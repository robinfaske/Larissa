"""Robustness checks for the working paper (Section 5).

Four independent checks, each returning a tidy frame the report script writes
to report/includes/ and the paper embeds:
  1. lambda_sensitivity  — refit with the decay pinned across its own history
  2. rolling_rmse        — fit-quality stability through time
  3. sampling_vol        — weekly- vs daily-sampled slope vol per trade
  4. reversion_counts    — count-based z-score mean-reversion check (no backtest)

None of these builds a P&L backtest; check 4 reports directional hit rates and
median moves only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src import analytics
from src.curves import ns_loadings

HORIZON_BD = 66  # 3 months in business days
TRADES = (("2s10s", 2.0, 10.0), ("5s10s", 5.0, 10.0))


def _refit_fixed_tau(curve: pd.DataFrame, tau: float) -> pd.DataFrame:
    """Refit Nelson-Siegel betas at every date with the decay pinned to `tau`."""
    rows = []
    for day, g in curve.groupby("date"):
        t = g["tenor_yrs"].to_numpy(float)
        y = g["yield_pct"].to_numpy(float)
        if len(t) < 4:
            continue
        betas, *_ = np.linalg.lstsq(ns_loadings(t, tau), y, rcond=None)
        rows.append({"date": day, "b0": betas[0], "b1": betas[1],
                     "b2": betas[2], "tau": tau})
    return pd.DataFrame(rows)


def _fitted_tau_history(curve: pd.DataFrame) -> np.ndarray:
    """Per-date free-decay NS fit; returns the fitted tau series."""
    from src.curves import fit_ns
    taus = []
    for _, g in curve.groupby("date"):
        t = g["tenor_yrs"].to_numpy(float)
        if len(t) < 4:
            continue
        taus.append(fit_ns(t, g["yield_pct"].to_numpy(float))["tau"])
    return np.array(taus)


def lambda_sensitivity(curves: dict[str, pd.DataFrame],
                       trade: dict[str, tuple[float, float]],
                       policy: dict[str, float]) -> pd.DataFrame:
    """Latest slope, z and carry with the decay pinned at the 10/50/90th
    percentiles of each curve's own fitted-decay history.

    The claim is invariance: a wide decay range should move the tradeable
    quantities by little relative to their levels.
    """
    rows = []
    for cc, (t_s, t_l) in trade.items():
        curve = curves[cc]
        pins = np.percentile(_fitted_tau_history(curve), [10, 50, 90])
        for pct, tau in zip((10, 50, 90), pins):
            fits = _refit_fixed_tau(curve, tau)
            slope = analytics.slope_series(fits, t_s, t_l)
            rows.append({
                "country": cc, "trade": f"{t_s:g}s{t_l:g}s",
                "pctile": f"p{pct}", "lambda": round(tau, 2),
                "slope_bp": round(slope.iloc[-1] * 100, 1),
                "z": round(analytics.slope_zscore(slope), 2),
                "carry_bp": round(analytics.trade_carry_roll_bp(
                    fits.iloc[-1], t_s, t_l, policy[cc], steepener=True), 1),
            })
    return pd.DataFrame(rows)


def rolling_rmse(fits_by_cc: dict[str, pd.DataFrame],
                 window: int = HORIZON_BD) -> pd.DataFrame:
    """Median and worst rolling-window fit RMSE per curve (fit-quality stability)."""
    rows = []
    for cc, fits in fits_by_cc.items():
        if "rmse_bp" not in fits:
            continue
        roll = fits["rmse_bp"].rolling(window, min_periods=window // 2).median().dropna()
        worst_at = fits.loc[roll.idxmax(), "date"] if len(roll) else None
        rows.append({
            "country": cc,
            "rmse_median_bp": round(float(fits["rmse_bp"].median()), 1),
            "rmse_roll_max_bp": round(float(roll.max()), 1) if len(roll) else float("nan"),
            "worst_window": f"{worst_at:%b %Y}" if worst_at is not None else "-",
        })
    return pd.DataFrame(rows)


def sampling_vol(fits_by_cc: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Daily- vs weekly-sampled 3m slope vol for every trade; ratio flags any
    stale-fill damping of the daily estimate (relevant for MX)."""
    rows = []
    for cc, fits in fits_by_cc.items():
        for name, t_s, t_l in TRADES:
            slope = analytics.slope_series(fits, t_s, t_l)
            daily = analytics.trade_vol_3m_bp(slope)
            weekly = analytics.weekly_vol_3m_bp(slope)
            rows.append({
                "country": cc, "trade": name,
                "vol_daily_bp": round(daily, 1), "vol_weekly_bp": round(weekly, 1),
                "ratio": round(weekly / daily, 2),
            })
    return pd.DataFrame(rows)


def _rolling_z(slope: pd.Series, min_bd: int = 252, years: int = 5) -> pd.Series:
    """Pointwise trailing z-score: each date scored on its prior `years` window."""
    s = slope.sort_index()
    s.index = pd.DatetimeIndex(s.index)
    out = {}
    for i, (day, val) in enumerate(s.items()):
        if i < min_bd:
            continue
        window = s.loc[day - pd.DateOffset(years=years):day]
        sd = window.std(ddof=1)
        if sd > 0:
            out[day] = (val - window.mean()) / sd
    return pd.Series(out)


def reversion_counts(fits_by_cc: dict[str, pd.DataFrame],
                     threshold: float = 1.0) -> pd.DataFrame:
    """Count-based mean-reversion check, pooled across all trades.

    For every date with |z| > threshold, does the slope move toward its mean
    over the next 66 business days? Reports event counts, the directional hit
    rate, and the median toward-mean move; the unconditional hit rate (50% by
    construction of a symmetric move) is the benchmark. No P&L, no positions.
    """
    rich_hits = rich_moves = rich_n = 0
    cheap_hits = cheap_moves = cheap_n = 0
    rich_deltas: list[float] = []
    cheap_deltas: list[float] = []
    for cc, fits in fits_by_cc.items():
        for _, t_s, t_l in TRADES:
            slope = analytics.slope_series(fits, t_s, t_l).sort_index()
            slope.index = pd.DatetimeIndex(slope.index)
            z = _rolling_z(slope)
            fwd = slope.reindex(z.index).shift(-HORIZON_BD) - slope.reindex(z.index)
            for day, zz in z.items():
                dv = fwd.get(day, np.nan)
                if np.isnan(dv):
                    continue
                if zz > threshold:  # steep/rich: expect flattening (dv < 0)
                    rich_n += 1
                    rich_hits += int(dv < 0)
                    rich_deltas.append(-dv * 100)  # bp toward mean
                elif zz < -threshold:  # flat/cheap: expect steepening (dv > 0)
                    cheap_n += 1
                    cheap_hits += int(dv > 0)
                    cheap_deltas.append(dv * 100)
    return pd.DataFrame([
        {"bucket": "z > +1 (steep)", "events": rich_n,
         "hit_rate": round(rich_hits / rich_n, 2) if rich_n else float("nan"),
         "median_toward_mean_bp": round(float(np.median(rich_deltas)), 1) if rich_deltas else float("nan")},
        {"bucket": "z < −1 (flat)", "events": cheap_n,
         "hit_rate": round(cheap_hits / cheap_n, 2) if cheap_n else float("nan"),
         "median_toward_mean_bp": round(float(np.median(cheap_deltas)), 1) if cheap_deltas else float("nan")},
    ])
