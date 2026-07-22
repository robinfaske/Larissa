"""Pipeline: cache -> fit -> analytics -> figures.

Offline by default (reads data/cache/). `--refresh` re-pulls every source
first; keys in .env are only needed for that path. Fails loudly with the
list of missing caches rather than running on partial data.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import analytics, fetchers
from src.curves import curve_at, fit_history
from src.plots import plot_carry_ranking, plot_curve_panels, plot_z_vs_cuts

PANEL_GRID = np.linspace(0.25, 10.0, 60)

DATASETS = {  # cache name -> fetcher
    "mx_curve": fetchers.fetch_mx_curve, "mx_policy": fetchers.fetch_mx_policy,
    "br_params": fetchers.fetch_br_params, "br_policy": fetchers.fetch_br_policy,
    "us_curve": fetchers.fetch_us_curve, "us_policy": fetchers.fetch_us_policy,
    "de_params": fetchers.fetch_de_params, "de_policy": fetchers.fetch_de_policy,
}


def refresh_all() -> None:
    for name, fn in DATASETS.items():
        if name == "de_params":
            try:
                fetchers.refresh(name, fn)
            except Exception as err:  # documented fallback, DECISIONS.md
                print(f"de_params failed ({err}); falling back to yield grid + refit")
                fetchers.refresh("de_curve", fetchers.fetch_de_yield_grid)
        else:
            fetchers.refresh(name, fn)
        print(f"refreshed {name}")


def load_all() -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """Return (fits_by_cc, policy_by_cc); raises listing every missing cache."""
    missing, fits, policy = [], {}, {}
    for cc, curve_name, kind in (("MX", "mx_curve", "fit"), ("US", "us_curve", "fit"),
                                 ("BR", "br_params", "published"),
                                 ("DE", "de_params", "published")):
        try:
            if kind == "fit":
                fits[cc] = fit_history(fetchers.load(curve_name))
            else:
                fits[cc] = fetchers.load(curve_name)
        except FileNotFoundError as err:
            if cc == "DE":  # fallback cache from refresh_all
                try:
                    fits[cc] = fit_history(fetchers.load("de_curve"))
                    continue
                except FileNotFoundError:
                    pass
            missing.append(str(err))
    for cc, name in (("MX", "mx_policy"), ("BR", "br_policy"),
                     ("US", "us_policy"), ("DE", "de_policy")):
        try:
            policy[cc] = fetchers.load(name)
        except FileNotFoundError as err:
            missing.append(str(err))
    if missing:
        raise SystemExit("missing caches:\n  " + "\n  ".join(missing))
    return fits, policy


def sanity_table(fits: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for cc, frame in fits.items():
        rows.append({
            "country": cc, "obs_days": len(frame),
            "first": frame["date"].min().date(), "last": frame["date"].max().date(),
            "y2_last_pct": round(float(curve_at(frame.iloc[-1], 2.0)[0]), 2),
            "y10_last_pct": round(float(curve_at(frame.iloc[-1], 10.0)[0]), 2),
            "rmse_bp_median": round(float(frame["rmse_bp"].median()), 1)
            if "rmse_bp" in frame else float("nan"),
        })
    return pd.DataFrame(rows)


def build_figures(fits: dict[str, pd.DataFrame], summary: pd.DataFrame) -> list[Path]:
    curves = {}
    for cc, frame in fits.items():
        today = frame.iloc[-1]
        past_idx = (frame["date"] - (today["date"] - pd.Timedelta(days=182))).abs().idxmin()
        curves[cc] = {"today": curve_at(today, PANEL_GRID),
                      "past": curve_at(frame.loc[past_idx], PANEL_GRID)}
    return [plot_curve_panels(curves, PANEL_GRID),
            plot_z_vs_cuts(summary),
            plot_carry_ranking(summary)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true",
                        help="re-pull all sources before running (needs .env keys)")
    args = parser.parse_args()
    if args.refresh:
        refresh_all()
    fits, policy = load_all()
    print("\n== data sanity ==")
    print(sanity_table(fits).to_string(index=False))
    summary = analytics.summary_table(fits, policy)
    print("\n== trade summary ==")
    print(summary.round(2).to_string(index=False))
    for path in build_figures(fits, summary):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
