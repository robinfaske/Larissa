"""Carry/rolldown math, DV01 neutrality, policy-path lens, basis conversions."""

import numpy as np
import pandas as pd
import pytest

from src import plots
from src.analytics import (dv01_neutral_ratio, forward_rate, invalidation_bp,
                           leg_carry_roll_bp, naive_cuts_bp, path_12m_bp,
                           slope_series, slope_zscore, summary_table,
                           trade_carry_roll_bp, weekly_vol_3m_bp, zero_dv01)
from src.curves import curve_at
from src.fetchers import semiannual_to_effective, simple_360_to_effective

UPWARD = pd.Series({"b0": 10.0, "b1": -3.0, "b2": 0.0, "tau": 1.5})  # rising curve
FLAT8 = pd.Series({"b0": 8.0, "b1": 0.0, "b2": 0.0, "tau": 1.5})


def test_dv01_neutral_weights_offset_exactly():
    ratio = dv01_neutral_ratio(8.0, 2.0, 7.0, 10.0)
    assert ratio * zero_dv01(8.0, 2.0) == pytest.approx(zero_dv01(7.0, 10.0))
    assert ratio > 1  # short leg needs more notional


def test_leg_carry_roll_matches_hand_formula():
    y10 = float(curve_at(UPWARD, 10.0)[0]) / 100
    y975 = float(curve_at(UPWARD, 9.75)[0]) / 100
    expected = (0.25 * (y10 - 0.07) + 9.75 * (y10 - y975)) * 1e4 / 10.0
    assert leg_carry_roll_bp(UPWARD, 10.0, 7.0) == pytest.approx(expected)
    assert expected > 0  # upward slope, funding below yield: positive carry+roll


def test_flat_curve_carry_is_pure_funding_spread():
    # no rolldown on a flat curve; carry = h*(y - r) spread over DV01
    assert leg_carry_roll_bp(FLAT8, 10.0, 8.0) == pytest.approx(0.0, abs=1e-9)
    assert leg_carry_roll_bp(FLAT8, 10.0, 7.0) == pytest.approx(
        0.25 * 0.01 * 1e4 / 10.0)


def test_steepener_flattener_are_signed_opposites():
    steep = trade_carry_roll_bp(UPWARD, 2.0, 10.0, 7.0, steepener=True)
    flat = trade_carry_roll_bp(UPWARD, 2.0, 10.0, 7.0, steepener=False)
    assert steep == pytest.approx(-flat)
    # funding below the front end: per unit DV01 the 2y leg out-carries the 10y
    # (carry scales with 1/T at equal DV01), so this steepener is carry-positive
    assert steep > 0


def test_policy_path_metrics():
    # flat curve: every forward equals the level, so no policy change priced
    assert forward_rate(FLAT8, 0.75, 1.0) == pytest.approx(8.0, abs=1e-9)
    assert path_12m_bp(FLAT8, 8.0) == pytest.approx(0.0, abs=1e-6)
    assert naive_cuts_bp(FLAT8, 8.0) == pytest.approx(0.0)
    inverted = pd.Series({"b0": 6.0, "b1": 2.0, "b2": 0.0, "tau": 1.0})
    assert path_12m_bp(inverted, 8.0) < -50  # forward path below policy = cuts
    # forward sits below both spot yields when the curve inverts locally
    assert forward_rate(inverted, 0.75, 1.0) < float(curve_at(inverted, 0.75)[0])


def test_basis_conversions():
    assert semiannual_to_effective(pd.Series([10.0]))[0] == pytest.approx(10.25)
    expected = ((1 + 0.10 * 91 / 360) ** (365 / 91) - 1) * 100
    assert simple_360_to_effective(pd.Series([10.0]), days=91)[0] == pytest.approx(expected)


def _synthetic_fits(seed: int, level: float) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end="2026-07-20", periods=400)
    slope = -3.0 + np.cumsum(rng.normal(0, 0.02, len(dates)))
    return pd.DataFrame({"date": dates, "b0": level, "b1": slope, "b2": 0.4,
                         "tau": 1.5, "rmse_bp": 2.0})


def test_summary_table_and_figures_end_to_end(tmp_path, monkeypatch):
    fits = {"MX": _synthetic_fits(1, 10.0), "BR": _synthetic_fits(2, 13.0)}
    policy = {cc: pd.DataFrame({"date": [pd.Timestamp("2026-07-20")], "rate_pct": [r]})
              for cc, r in (("MX", 8.0), ("BR", 12.0))}
    summary = summary_table(fits, policy)
    assert len(summary) == 4  # 2 countries x (2s10s, 5s10s)
    assert set(summary["trade"]) == {"2s10s", "5s10s"}
    assert summary["vol_3m_bp"].gt(0).all() and summary["vol_wk_3m_bp"].gt(0).all()
    # invalidation sits 1 sigma against each trade's positive-carry direction
    mx = slope_series(fits["MX"], 2.0, 10.0)
    row = summary.loc[summary.eval("country=='MX' and trade=='2s10s'")].iloc[0]
    expected = invalidation_bp(mx, steepener=row["steepener_carry_roll_bp_3m"] >= 0)
    assert row["inval_bp"] == pytest.approx(expected)
    assert weekly_vol_3m_bp(mx) > 0
    z = slope_zscore(slope_series(fits["MX"], 2.0, 10.0))
    assert summary.loc[summary.eval("country=='MX' and trade=='2s10s'"),
                       "slope_z"].iloc[0] == pytest.approx(z)
    monkeypatch.setattr(plots, "FIG_DIR", tmp_path)
    grid = np.linspace(0.25, 10, 40)
    curves = {cc: {"grid": grid, "today": curve_at(f.iloc[-1], grid),
                   "past": curve_at(f.iloc[0], grid)}
              for cc, f in fits.items()}
    for path in (plots.plot_curve_panels(curves), plots.plot_z_vs_cuts(summary),
                 plots.plot_carry_ranking(summary)):
        assert path.exists() and path.stat().st_size > 10_000
