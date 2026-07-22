"""Curve fitting recovers known synthetic curves."""

import numpy as np
import pandas as pd
import pytest

from src.curves import curve_at, fit_history, fit_ns, fit_nss, ns_yield, svensson_yield

TENORS = np.array([0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30], dtype=float)


def test_ns_fit_recovers_synthetic_curve():
    true = {"b0": 9.0, "b1": -2.5, "b2": 1.8, "tau": 1.7}
    yields = ns_yield(TENORS, **true)
    fit = fit_ns(TENORS, yields)
    assert fit["rmse_bp"] < 1.0
    grid = np.linspace(0.25, 30, 50)
    refit = ns_yield(grid, fit["b0"], fit["b1"], fit["b2"], fit["tau"])
    assert np.max(np.abs(refit - ns_yield(grid, **true))) < 0.02  # 2bp off-grid


def test_nss_fit_recovers_synthetic_curve():
    true = dict(b0=8.0, b1=-3.0, b2=2.0, b3=-1.5, t1=1.2, t2=6.0)
    yields = svensson_yield(TENORS, **true)
    fit = fit_nss(TENORS, yields)
    assert fit["rmse_bp"] < 1.0


def test_fit_history_returns_beta_series_and_rmse():
    dates = pd.bdate_range("2025-01-01", periods=5)
    rows = [(d, t, float(ns_yield(t, 9.0 + 0.01 * i, -2.0, 1.0, 1.5)[0]))
            for i, d in enumerate(dates) for t in TENORS]
    fits = fit_history(pd.DataFrame(rows, columns=["date", "tenor_yrs", "yield_pct"]))
    assert list(fits["date"]) == list(dates)
    assert (fits["rmse_bp"] < 1.0).all()
    assert fits["b0"].is_monotonic_increasing  # tracks the drifting level


def test_fit_history_rejects_sparse_curves():
    frame = pd.DataFrame({"date": [pd.Timestamp("2025-01-01")] * 3,
                          "tenor_yrs": [1.0, 5.0, 10.0], "yield_pct": [5, 6, 7]})
    with pytest.raises(ValueError):
        fit_history(frame)


def test_curve_at_dispatches_ns_and_nss():
    ns_row = pd.Series({"b0": 9.0, "b1": -2.5, "b2": 1.8, "tau": 1.7, "b3": np.nan})
    assert curve_at(ns_row, 10.0) == pytest.approx(ns_yield(10.0, 9.0, -2.5, 1.8, 1.7)[0])
    nss_row = pd.Series(dict(b0=8.0, b1=-3.0, b2=2.0, b3=-1.5, t1=1.2, t2=6.0))
    assert curve_at(nss_row, 10.0) == pytest.approx(
        svensson_yield(10.0, 8.0, -3.0, 2.0, -1.5, 1.2, 6.0)[0])
