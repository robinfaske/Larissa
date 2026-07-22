"""Nelson-Siegel and Svensson curve fitting.

Fits are linear in the betas once the decay parameters are fixed, so we grid
tau over a bounded, economically sensible range and solve ordinary least
squares at each grid point — no fragile nonlinear optimizer, fully
reproducible. RMSE is reported per fit (in bp) so bad days are visible.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TAU_GRID = np.geomspace(0.15, 5.0, 40)  # decay in years; covers 2m-5y humps
TAU2_GRID = np.geomspace(2.0, 12.0, 12)  # second Svensson hump, longer end


def ns_loadings(tenors: np.ndarray, tau: float) -> np.ndarray:
    """Nelson-Siegel design matrix [level, slope, curvature] for tenors (years)."""
    x = np.asarray(tenors, dtype=float) / tau
    decay = (1 - np.exp(-x)) / x
    return np.column_stack([np.ones_like(x), decay, decay - np.exp(-x)])


def ns_yield(tenors: np.ndarray | float, b0: float, b1: float, b2: float,
             tau: float) -> np.ndarray:
    """Evaluate a fitted Nelson-Siegel curve, in the same units it was fit in (%)."""
    t = np.atleast_1d(np.asarray(tenors, dtype=float))
    return ns_loadings(t, tau) @ np.array([b0, b1, b2])


def svensson_yield(tenors: np.ndarray | float, b0: float, b1: float, b2: float,
                   b3: float, t1: float, t2: float) -> np.ndarray:
    """Evaluate a Svensson curve from published or fitted parameters (%)."""
    t = np.atleast_1d(np.asarray(tenors, dtype=float))
    base = ns_loadings(t, t1) @ np.array([b0, b1, b2])
    x2 = t / t2
    return base + b3 * ((1 - np.exp(-x2)) / x2 - np.exp(-x2))


def fit_ns(tenors: np.ndarray, yields: np.ndarray) -> dict:
    """Fit NS by gridded tau + OLS betas. Returns params and RMSE in bp."""
    best = None
    for tau in TAU_GRID:
        design = ns_loadings(tenors, tau)
        betas, *_ = np.linalg.lstsq(design, yields, rcond=None)
        rmse = float(np.sqrt(np.mean((design @ betas - yields) ** 2)))
        if best is None or rmse < best["rmse_bp"] / 100.0:
            best = {"b0": betas[0], "b1": betas[1], "b2": betas[2],
                    "tau": float(tau), "rmse_bp": rmse * 100.0}
    return best


def fit_nss(tenors: np.ndarray, yields: np.ndarray) -> dict:
    """Fit Svensson the same way over a (tau1, tau2) grid. Needs >= 6 tenors."""
    best = None
    for t1 in TAU_GRID:
        base = ns_loadings(tenors, t1)
        for t2 in TAU2_GRID:
            x2 = tenors / t2
            design = np.column_stack([base, (1 - np.exp(-x2)) / x2 - np.exp(-x2)])
            betas, *_ = np.linalg.lstsq(design, yields, rcond=None)
            rmse = float(np.sqrt(np.mean((design @ betas - yields) ** 2)))
            if best is None or rmse < best["rmse_bp"] / 100.0:
                best = {"b0": betas[0], "b1": betas[1], "b2": betas[2], "b3": betas[3],
                        "t1": float(t1), "t2": float(t2), "rmse_bp": rmse * 100.0}
    return best


def fit_history(curve: pd.DataFrame, min_tenors: int = 5) -> pd.DataFrame:
    """Fit every date in a tidy curve frame; NSS when >= 6 tenors, else NS.

    Returns one row per date with parameters, model tag, and rmse_bp — the
    stored beta time series required by the method spec.
    """
    rows = []
    for day, group in curve.groupby("date"):
        tenors = group["tenor_yrs"].to_numpy(dtype=float)
        yields = group["yield_pct"].to_numpy(dtype=float)
        if len(tenors) < min_tenors:
            continue
        if len(tenors) >= 6:
            fit = fit_nss(tenors, yields) | {"model": "nss"}
        else:
            fit = fit_ns(tenors, yields) | {"model": "ns"}
        rows.append({"date": day} | fit)
    if not rows:
        raise ValueError("no dates with enough tenors to fit")
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def curve_at(fit: dict | pd.Series, tenors: np.ndarray | float) -> np.ndarray:
    """Evaluate one fitted row (from fit_history or a published-params frame)."""
    if "b3" in fit and not pd.isna(fit["b3"]):
        t1 = fit["t1"] if "t1" in fit else fit["tau"]
        return svensson_yield(tenors, fit["b0"], fit["b1"], fit["b2"], fit["b3"],
                              t1, fit["t2"])
    return ns_yield(tenors, fit["b0"], fit["b1"], fit["b2"],
                    fit["tau"] if "tau" in fit else fit["t1"])
