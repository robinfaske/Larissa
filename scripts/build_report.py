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
    if round(x, dp) == 0:
        x = abs(x)  # avoid "−0.0"
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
    chg3m = (br5.diff(66).dropna() * 100)
    worst = chg3m[chg3m.index >= chg3m.index.max() - pd.DateOffset(years=5)]
    var("kill_worst3m", fmt(float(worst.min()), 1, sign=True),
        "min 66-bday change of BR 5s10s slope, 5y window")
    var("kill_worst3m_when", f"{worst.idxmin():%b %Y}", "date of that worst 3m flattening")
    var("rb_5s10s", fmt(RETAIL_BASIS_BP["10y"] - RETAIL_BASIS_BP["5y"], 1, sign=True),
        "retail-basis differential 10y minus 5y (slope mismeasurement)")
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

    _write_vars_provenance(rows)
    return rows


def _write_vars_provenance(rows: list[tuple]) -> None:
    body = "\n".join(f'  {n}: "{v}",' for n, v, _ in rows)
    (INC / "vars.typ").write_text(f"#let n = (\n{body}\n)\n")
    pd.DataFrame(rows, columns=["variable", "value", "source"]).to_csv(
        INC / "provenance.csv", index=False)


def build_robustness(fits: dict, policy: dict) -> list[tuple]:
    """Compute the four Section-5 checks, write their CSVs, return extra vars."""
    from src import fetchers, robustness
    pol = {cc: analytics.latest_policy(policy[cc]) for cc in fits}
    curves = {"BR": fetchers.load("br_curve"), "US": fetchers.load("us_curve"),
              "MX": fetchers.ffill_panel(fetchers.load("mx_curve"))}

    samp = robustness.sampling_vol(fits)
    rmse = robustness.rolling_rmse(fits)
    rev = robustness.reversion_counts(fits)
    lam = robustness.lambda_sensitivity(
        curves, {"BR": (5.0, 10.0), "MX": (2.0, 10.0), "US": (5.0, 10.0)}, pol)
    _minus = lambda s: s.astype(str).str.replace("-", "−", regex=False)
    pd.DataFrame({
        "Country": lam["country"], "Trade": lam["trade"], "Pctile": lam["pctile"],
        "λ (yrs)": lam["lambda"].map(lambda x: f"{x:.2f}"),
        "Slope bp": _minus(lam["slope_bp"].map(lambda x: f"{x:+.1f}")),
        "z (5y)": _minus(lam["z"].map(lambda x: f"{x:+.2f}")),
        "Carry bp": _minus(lam["carry_bp"].map(lambda x: f"{x:+.1f}")),
    }).to_csv(INC / "rob_lambda.csv", index=False)
    pd.DataFrame({
        "Curve": rmse["country"], "Median RMSE bp": rmse["rmse_median_bp"],
        "Worst 66d RMSE bp": rmse["rmse_roll_max_bp"], "Worst window": rmse["worst_window"],
    }).to_csv(INC / "rob_rmse.csv", index=False)
    pd.DataFrame({
        "Country": samp["country"], "Trade": samp["trade"],
        "Vol daily bp": samp["vol_daily_bp"], "Vol weekly bp": samp["vol_weekly_bp"],
        "Weekly / daily": samp["ratio"].map(lambda x: f"{x:.2f}"),
    }).to_csv(INC / "rob_sampling.csv", index=False)
    pd.DataFrame({
        "Bucket": rev["bucket"], "Events": rev["events"],
        "Toward-mean hit rate": rev["hit_rate"].map(lambda x: f"{x:.2f}"),
        "Median move bp": _minus(rev["median_toward_mean_bp"].map(lambda x: f"{x:+.1f}")),
    }).to_csv(INC / "rob_reversion.csv", index=False)

    rich = rev.iloc[0]
    cheap = rev.iloc[1]
    br_lam = lam[lam["country"] == "BR"]
    br_rmse = rmse[rmse["country"] == "BR"].iloc[0]
    rows = [
        ("rob_rich_n", f"{int(rich['events'])}", "robustness.reversion_counts, z>+1 events"),
        ("rob_rich_hit", fmt(rich["hit_rate"], 2), "toward-mean hit rate, z>+1"),
        ("rob_rich_move", fmt(rich["median_toward_mean_bp"], 1), "median toward-mean move, z>+1"),
        ("rob_cheap_n", f"{int(cheap['events'])}", "robustness.reversion_counts, z<−1 events"),
        ("rob_cheap_hit", fmt(cheap["hit_rate"], 2), "toward-mean hit rate, z<−1"),
        ("rob_br_carry_lo", fmt(br_lam["carry_bp"].min(), 1), "BR carry, min over pinned λ"),
        ("rob_br_carry_hi", fmt(br_lam["carry_bp"].max(), 1), "BR carry, max over pinned λ"),
        ("rob_br_rmse_max", fmt(br_rmse["rmse_roll_max_bp"], 1), "BR worst 66d rolling RMSE"),
        ("rob_br_rmse_when", br_rmse["worst_window"], "date of BR worst rolling RMSE"),
    ]
    return rows


def _compile(typ: Path, out: Path) -> None:
    out.write_bytes(typst.compile(str(typ), root=str(ROOT),
                                  font_paths=[str(ROOT / "assets" / "fonts")]))
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")


def _thumbnail(pdf: Path, png: Path, scale: float = 1.2) -> None:
    try:
        import pypdfium2 as pdfium
        pdfium.PdfDocument(str(pdf))[0].render(scale=scale).to_pil().save(png)
        print(f"wrote {png}")
    except ImportError:
        print("pypdfium2 not installed — skipped thumbnail")


def build_paper_figures(fits: dict, summary: pd.DataFrame) -> None:
    """Regenerate the three figures at paper column widths (no post-scaling)."""
    from src import plots, theme
    figdir = ROOT / "paper" / "figs"
    grid_start = {"BR": 0.5}
    curves = {}
    for cc, frame in fits.items():
        today = frame.iloc[-1]
        past = (frame["date"] - (today["date"] - pd.Timedelta(days=182))).abs().idxmin()
        import numpy as np
        g = np.linspace(grid_start.get(cc, 0.25), 10.0, 60)
        curves[cc] = {"grid": g, "today": curve_at(today, g), "past": curve_at(frame.loc[past], g)}
    plots.plot_curve_panels(curves, width_in=theme.PAPER_TEXT_IN, fig_dir=figdir)
    plots.plot_z_vs_cuts(summary, width_in=theme.PAPER_FIG_IN, fig_dir=figdir)
    plots.plot_carry_ranking(summary, width_in=theme.PAPER_TEXT_IN, fig_dir=figdir)


def main() -> None:
    fits, policy = run_all.load_all()
    summary = analytics.summary_table(fits, policy)
    run_all.build_figures(fits, summary)
    rows = write_includes(fits, policy, summary)
    rows = rows + build_robustness(fits, policy)
    _write_vars_provenance(rows)  # rewrite with robustness vars appended
    print(f"{len(rows)} variables ->", INC / "vars.typ")

    _compile(ROOT / "report" / "note.typ", ROOT / "report" / "note.pdf")
    _thumbnail(ROOT / "report" / "note.pdf", ROOT / "report" / "note_page1.png")

    paper = ROOT / "paper" / "paper.typ"
    if paper.exists():
        build_paper_figures(fits, summary)
        _compile(paper, ROOT / "paper" / "paper.pdf")
        _thumbnail(ROOT / "paper" / "paper.pdf", ROOT / "paper" / "paper_page1.png")


if __name__ == "__main__":
    main()
