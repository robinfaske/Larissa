"""Trade analytics: carry, rolldown, slope z-scores, policy path, vol sizing.

Conventions (derivation in DECISIONS.md):
- Legs are zero-coupon approximations sized to one unit of DV01, so a trade
  P&L in bp equals the move in its fitted yield spread.
- Carry+rolldown is 3m static (curve unchanged), funded at the policy rate,
  quoted in bp per 3m per unit DV01.
- Steepener = long the short-tenor leg, short the long-tenor leg; a positive
  number is money earned by the steepener.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.curves import curve_at

HORIZON = 0.25          # 3m, years
BDAYS_3M = 66
ZSCORE_YEARS = 5


def zero_dv01(y_pct: float, tenor_yrs: float, notional: float = 100.0) -> float:
    """DV01 of a zero-coupon bond (currency per 1bp yield move)."""
    y = y_pct / 100.0
    price = notional / (1 + y) ** tenor_yrs
    return price * tenor_yrs / (1 + y) * 1e-4


def dv01_neutral_ratio(y_short_pct: float, t_short: float,
                       y_long_pct: float, t_long: float) -> float:
    """Notional of the short-tenor leg per 1 notional of the long-tenor leg."""
    return zero_dv01(y_long_pct, t_long) / zero_dv01(y_short_pct, t_short)


def leg_carry_roll_bp(fit: pd.Series, tenor_yrs: float, policy_pct: float,
                      h: float = HORIZON) -> float:
    """3m static carry + rolldown of a long position, bp per unit DV01.

    excess return ~= h*(y_T - r) + (T-h)*(y_T - y_{T-h}); divided by DV01
    per notional (T * 1e-4) to express in bp.
    """
    y_t = float(curve_at(fit, tenor_yrs)[0]) / 100.0
    y_roll = float(curve_at(fit, tenor_yrs - h)[0]) / 100.0
    r = policy_pct / 100.0
    excess = h * (y_t - r) + (tenor_yrs - h) * (y_t - y_roll)
    return excess * 1e4 / tenor_yrs


def trade_carry_roll_bp(fit: pd.Series, t_short: float, t_long: float,
                        policy_pct: float, steepener: bool = True) -> float:
    """DV01-neutral curve trade carry+roll, bp per 3m per unit DV01 per leg."""
    spread = (leg_carry_roll_bp(fit, t_short, policy_pct)
              - leg_carry_roll_bp(fit, t_long, policy_pct))
    return spread if steepener else -spread


def slope_series(fits: pd.DataFrame, t_short: float, t_long: float) -> pd.Series:
    """Fitted slope (long minus short tenor, %) as a date-indexed series."""
    values = [float(curve_at(row, t_long)[0] - curve_at(row, t_short)[0])
              for _, row in fits.iterrows()]
    return pd.Series(values, index=fits["date"].values, name="slope_pct")


def slope_zscore(slope: pd.Series, years: int = ZSCORE_YEARS) -> float:
    """Latest slope vs its own trailing history, in standard deviations."""
    window = slope[slope.index >= slope.index.max() - pd.DateOffset(years=years)]
    if len(window) < 60:
        raise ValueError(f"only {len(window)} obs in z-score window — not enough history")
    return float((window.iloc[-1] - window.mean()) / window.std(ddof=1))


def cuts_priced_12m_bp(fit: pd.Series, policy_pct: float) -> float:
    """Easing priced over the next 12m, bp; negative = cuts priced.

    Reads the fitted 1y yield as the average expected policy rate over the
    year and assumes a linear path (DECISIONS.md), so the implied end-point
    is policy + 2*(y1y - policy).
    """
    y1 = float(curve_at(fit, 1.0)[0])
    return 2.0 * (y1 - policy_pct) * 100.0


def trade_vol_3m_bp(slope: pd.Series) -> float:
    """Realized 3m vol of the trade: stdev of daily slope changes * sqrt(66), bp."""
    daily = slope.sort_index().diff().dropna()
    recent = daily[daily.index >= daily.index.max() - pd.DateOffset(years=1)]
    return float(recent.std(ddof=1) * np.sqrt(BDAYS_3M) * 100.0)


def latest_policy(policy: pd.DataFrame) -> float:
    return float(policy.sort_values("date")["rate_pct"].iloc[-1])


def summary_table(fits_by_cc: dict[str, pd.DataFrame],
                  policy_by_cc: dict[str, pd.DataFrame],
                  trades: tuple[tuple[float, float], ...] = ((2.0, 10.0), (5.0, 10.0)),
                  ) -> pd.DataFrame:
    """One row per country x trade: slope, z, cuts priced, carry+roll, vol, ratio.

    carry_roll_bp is quoted for the steepener; a negative number means the
    flattener earns it instead. ratio = carry_roll / vol for whichever
    direction is positive-carry, signed + for steepener, - for flattener.
    """
    rows = []
    for cc, fits in fits_by_cc.items():
        latest = fits.iloc[-1]
        policy = latest_policy(policy_by_cc[cc])
        for t_short, t_long in trades:
            slope = slope_series(fits, t_short, t_long)
            carry = trade_carry_roll_bp(latest, t_short, t_long, policy, steepener=True)
            vol = trade_vol_3m_bp(slope)
            rows.append({
                "country": cc, "trade": f"{t_short:g}s{t_long:g}s",
                "slope_bp": slope.iloc[-1] * 100.0,
                "slope_z": slope_zscore(slope),
                "cuts_priced_12m_bp": cuts_priced_12m_bp(latest, policy),
                "steepener_carry_roll_bp_3m": carry,
                "vol_3m_bp": vol,
                "carry_per_vol": carry / vol,
                "fit_rmse_bp": latest.get("rmse_bp", float("nan")),
            })
    return pd.DataFrame(rows)
