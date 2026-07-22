"""Robustness checks: shapes, invariants, and the mean-reversion accounting."""

import numpy as np
import pandas as pd
import pytest

from src import robustness
from src.curves import ns_yield


def _synthetic_curve(seed: int, level: float, n_days: int = 400) -> pd.DataFrame:
    """A tidy curve frame with a drifting slope, 9 tenors per date."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end="2026-07-20", periods=n_days)
    tenors = np.array([0.25, 0.5, 1, 2, 3, 5, 7, 10, 20], dtype=float)
    b1 = -3.0 + np.cumsum(rng.normal(0, 0.03, n_days))
    rows = []
    for d, slope in zip(dates, b1):
        for t in tenors:
            rows.append((d, t, float(ns_yield(t, level, slope, 1.0, 1.5)[0])))
    return pd.DataFrame(rows, columns=["date", "tenor_yrs", "yield_pct"])


def _synthetic_fits(seed: int, level: float, n_days: int = 500) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end="2026-07-20", periods=n_days)
    slope = -3.0 + np.cumsum(rng.normal(0, 0.02, n_days))
    return pd.DataFrame({"date": dates, "b0": level, "b1": slope, "b2": 0.4,
                         "tau": 1.5, "rmse_bp": 2.0 + np.abs(rng.normal(0, 0.5, n_days))})


def test_sampling_vol_shape_and_positivity():
    fits = {"MX": _synthetic_fits(1, 10.0), "BR": _synthetic_fits(2, 13.0)}
    out = robustness.sampling_vol(fits)
    assert len(out) == 4  # 2 countries x 2 trades
    assert (out["vol_daily_bp"] > 0).all() and (out["vol_weekly_bp"] > 0).all()
    assert (out["ratio"] > 0).all()


def test_rolling_rmse_bounds():
    fits = {"MX": _synthetic_fits(1, 10.0)}
    out = robustness.rolling_rmse(fits)
    row = out.iloc[0]
    # worst rolling median is >= the full-sample median for a noisy series
    assert row["rmse_roll_max_bp"] >= row["rmse_median_bp"]


def test_reversion_counts_are_valid_rates():
    fits = {"MX": _synthetic_fits(1, 10.0), "BR": _synthetic_fits(2, 13.0),
            "US": _synthetic_fits(3, 4.0), "DE": _synthetic_fits(4, 2.5)}
    out = robustness.reversion_counts(fits)
    assert set(out["bucket"]) == {"z > +1 (steep)", "z < −1 (flat)"}
    for _, r in out.iterrows():
        assert r["events"] >= 0
        if r["events"] > 0:
            assert 0.0 <= r["hit_rate"] <= 1.0


def test_lambda_sensitivity_pins_and_reports():
    curves = {"BR": _synthetic_curve(2, 13.0)}
    out = robustness.lambda_sensitivity(curves, {"BR": (5.0, 10.0)}, {"BR": 12.0})
    assert list(out["pctile"]) == ["p10", "p50", "p90"]
    assert out["lambda"].is_monotonic_increasing  # percentiles ordered
    # carry is finite and reported per pin
    assert out["carry_bp"].notna().all()


def test_refit_fixed_tau_recovers_betas():
    # a curve generated at tau=1.5 should refit near its true betas when pinned
    curve = _synthetic_curve(7, 9.0, n_days=5)
    fits = robustness._refit_fixed_tau(curve, 1.5)
    assert len(fits) == 5
    assert fits["b0"].between(8.0, 10.0).all()  # level recovered near 9
