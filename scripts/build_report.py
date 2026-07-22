"""Build the research note: cache -> analytics -> Typst includes -> PDF.

Every figure, table, and inline number in report/note.typ comes from the
include files generated here — nothing hand-typed. Each variable carries a
provenance entry mapping it to its analytics source; the build prints that
table and writes it into the appendix.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import typst

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import run_all
from src import analytics
from src.curves import curve_at

INC = ROOT / "report" / "includes"

# One-off cross-check vs ANBIMA's published interbank params (2026-07-17),
# not recomputable offline — ANBIMA's public window rolls (DECISIONS.md).
RETAIL_BASIS_BP = {"1y": -7.6, "5y": -23.1, "10y": -19.3}


def fmt(x: float, dp: int = 1, sign: bool = False) -> str:
    s = f"{x:+.{dp}f}" if sign else f"{x:.{dp}f}"
    return s.replace("-", "−")  # typographic minus


def build_vars(fits: dict, policy: dict, summary: pd.DataFrame) -> list[tuple[str, str, str]]:
    """(name, formatted value, provenance) for every inline number."""
    rows: list[tuple[str, str, str]] = []

    def var(name: str, value: str, source: str) -> None:
        rows.append((name, value, source))

    br, mx = fits["BR"], fits["MX"]
    s = {(r["country"], r["trade"]): r for _, r in summary.iterrows()}
    b, m = s[("BR", "5s10s")], s[("MX", "2s10s")]
    br5 = analytics.slope_series(br, 5.0, 10.0)
    br5.index = pd.DatetimeIndex(br5.index)
    win = br5[br5.index >= br5.index.max() - pd.DateOffset(years=5)]
    y5, y10 = (float(curve_at(br.iloc[-1], t)[0]) for t in (5.0, 10.0))

    var("date", f"{br.iloc[-1]['date']:%d %b %Y}", "last cached BR fit date")
    for cc in ("BR", "MX", "US", "DE"):
        var(f"{cc.lower()}_policy", fmt(analytics.latest_policy(policy[cc]), 2),
            f"fetchers.load('{cc.lower()}_policy'), latest, effective annual")
    var("br_path12", fmt(b["path_12m_bp"], 1, sign=True),
        "analytics.path_12m_bp(BR latest fit, policy)")
    var("br_naive", fmt(b["naive_cuts_bp"], 1, sign=True),
        "analytics.naive_cuts_bp — appendix comparison only")
    var("br_slope", fmt(b["slope_bp"], 1, sign=True), "BR 5s10s fitted slope, latest")
    var("br_slope_mean5y", fmt(win.mean() * 100, 1, sign=True), "5y mean of BR 5s10s slope")
    var("br_sigma5y", fmt(win.std(ddof=1) * 100, 1), "5y stdev of BR 5s10s slope levels")
    var("br_z", fmt(b["slope_z"], 2, sign=True), "analytics.slope_zscore(BR 5s10s)")
    var("br_carry", fmt(b["steepener_carry_roll_bp_3m"], 1, sign=True),
        "analytics.trade_carry_roll_bp(BR, 5, 10, steepener)")
    var("br_vol", fmt(b["vol_3m_bp"], 1), "analytics.trade_vol_3m_bp(BR 5s10s)")
    var("br_vol_wk", fmt(b["vol_wk_3m_bp"], 1), "analytics.weekly_vol_3m_bp(BR 5s10s)")
    var("br_cv", fmt(b["carry_per_vol"], 2), "carry / vol, BR 5s10s steepener")
    var("br_inval", fmt(b["inval_bp"], 1, sign=True), "analytics.invalidation_bp(BR 5s10s)")
    var("br_y5", fmt(y5, 2), "fitted BR 5y yield, latest")
    var("br_y10", fmt(y10, 2), "fitted BR 10y yield, latest")
    var("br_ratio", fmt(analytics.dv01_neutral_ratio(y5, 5.0, y10, 10.0), 2),
        "analytics.dv01_neutral_ratio — 5y notional per 1.00 of 10y")
    var("br_rmse", fmt(float(br["rmse_bp"].median()), 1), "median BR fit RMSE")

    var("mx_cv", fmt(m["carry_per_vol"], 2), "carry / vol, MX 2s10s steepener")
    var("mx_carry", fmt(m["steepener_carry_roll_bp_3m"], 1, sign=True),
        "analytics.trade_carry_roll_bp(MX, 2, 10, steepener)")
    var("mx_vol", fmt(m["vol_3m_bp"], 1), "analytics.trade_vol_3m_bp(MX 2s10s)")
    var("mx_vol_wk", fmt(m["vol_wk_3m_bp"], 1), "analytics.weekly_vol_3m_bp(MX 2s10s)")
    var("mx_z", fmt(m["slope_z"], 2, sign=True), "analytics.slope_zscore(MX 2s10s)")
    var("mx_slope", fmt(m["slope_bp"], 1, sign=True), "MX 2s10s fitted slope, latest")
    var("mx_path12", fmt(m["path_12m_bp"], 1, sign=True), "analytics.path_12m_bp(MX)")

    us5 = analytics.slope_series(fits["US"], 5.0, 10.0)
    us5.index = pd.DatetimeIndex(us5.index)
    box = (br5 - us5).dropna()
    var("box_level", fmt(box.iloc[-1] * 100, 1, sign=True), "BR minus US 5s10s fitted slope")
    var("box_z", fmt(analytics.slope_zscore(box), 2, sign=True),
        "analytics.slope_zscore(BR−US 5s10s box)")
    var("box_corr", fmt(br5.diff().corr(us5.diff()), 2), "daily slope-change correlation")

    kill_move = b["inval_bp"] - b["slope_bp"]
    var("kill_move", fmt(kill_move, 1, sign=True), "invalidation minus entry slope")
    var("kill_quarters", fmt(abs(kill_move) / b["steepener_carry_roll_bp_3m"], 1),
        "|invalidation move| / quarterly carry")
    front = analytics.slope_series(br, 0.25, 2.0)
    beta = br5.diff().cov(front.diff()) / front.diff().var()
    var("kill_beta", fmt(beta, 2),
        "cov/var of daily d(5s10s) on d(3m2y front slope), full sample")
    for k, v in RETAIL_BASIS_BP.items():
        var(f"rb_{k}", fmt(v, 1, sign=True), "DECISIONS.md one-off ANBIMA cross-check")
    return rows


def write_includes(fits: dict, policy: dict, summary: pd.DataFrame) -> list[tuple]:
    INC.mkdir(parents=True, exist_ok=True)
    rows = build_vars(fits, policy, summary)
    body = "\n".join(f'  {n}: "{v}",' for n, v, _ in rows)
    (INC / "vars.typ").write_text(f"#let n = (\n{body}\n)\n")

    disp = pd.DataFrame({
        "Trade": summary["country"] + " " + summary["trade"],
        "Policy %": [fmt(analytics.latest_policy(policy[c]), 2) for c in summary["country"]],
        "Path 12m bp": [fmt(x, 0, sign=True) for x in summary["path_12m_bp"]],
        "Slope bp": [fmt(x, 0, sign=True) for x in summary["slope_bp"]],
        "z (5y)": [fmt(x, 2, sign=True) for x in summary["slope_z"]],
        "C+R bp/3m": [fmt(x, 1, sign=True) for x in summary["steepener_carry_roll_bp_3m"]],
        "Vol bp": [fmt(x, 0) for x in summary["vol_3m_bp"]],
        "C/V": [fmt(x, 2) for x in summary["carry_per_vol"]],
        "Exit bp": [fmt(x, 0, sign=True) for x in summary["inval_bp"]],
    })
    disp.to_csv(INC / "summary.csv", index=False)

    fit_rows = []
    for cc, frame in fits.items():
        fit_rows.append({
            "Curve": cc, "Days": len(frame),
            "Median RMSE bp": fmt(float(frame["rmse_bp"].median()), 1)
            if "rmse_bp" in frame else "published params",
        })
    pd.DataFrame(fit_rows).to_csv(INC / "rmse.csv", index=False)

    naive = summary.drop_duplicates("country")
    pd.DataFrame({
        "Country": naive["country"],
        "Forward-path bp": [fmt(x, 1, sign=True) for x in naive["path_12m_bp"]],
        "Naive 2x(1y-policy) bp": [fmt(x, 1, sign=True) for x in naive["naive_cuts_bp"]],
    }).to_csv(INC / "path_compare.csv", index=False)

    pd.DataFrame(rows, columns=["variable", "value", "source"]).to_csv(
        INC / "provenance.csv", index=False)
    return rows


def main() -> None:
    fits, policy = run_all.load_all()
    summary = analytics.summary_table(fits, policy)
    run_all.build_figures(fits, summary)
    rows = write_includes(fits, policy, summary)
    print(f"{len(rows)} variables ->", INC / "vars.typ")
    print(pd.DataFrame(rows, columns=["variable", "value", "source"]).to_string(index=False))
    pdf = typst.compile(str(ROOT / "report" / "note.typ"), root=str(ROOT))
    out = ROOT / "report" / "note.pdf"
    out.write_bytes(pdf)
    print(f"wrote {out} ({len(pdf):,} bytes)")


if __name__ == "__main__":
    main()
