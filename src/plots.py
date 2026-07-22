"""Figure factory: three charts, one palette, sized for a 2-page PDF note.

Colors follow the entity: each country keeps one hue across all figures
(anchors muted gray so the EM story carries the color). Palette slots and
chrome follow a CVD-validated reference palette; identity is never
color-alone — every mark is direct-labeled.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

FIG_DIR = Path(__file__).resolve().parent.parent / "output" / "figs"

COUNTRY_COLORS = {  # fixed assignment, never cycled
    "MX": "#2a78d6", "BR": "#eb6834", "PL": "#1baf7a", "HU": "#eda100",
    "TR": "#e87ba4", "US": "#898781", "DE": "#898781",
}
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"

STYLE = {
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "font.family": "sans-serif", "font.size": 8.5,
    "text.color": INK, "axes.labelcolor": INK2,
    "axes.edgecolor": BASELINE, "axes.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.titlesize": 9.5, "axes.titleweight": "bold",
    "legend.frameon": False, "legend.fontsize": 8,
}


def _save(fig: plt.Figure, name: str) -> Path:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = FIG_DIR / f"{name}.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_curve_panels(curves: dict[str, dict[str, np.ndarray]],
                      grid: np.ndarray) -> Path:
    """Chart 1 — small multiples: fitted curve today vs 6m ago, per country.

    `curves[cc]` holds arrays 'today' and 'past' evaluated on `grid` (years).
    """
    with plt.rc_context(STYLE):
        cols = min(len(curves), 3)
        rows = -(-len(curves) // cols)
        fig, axes = plt.subplots(rows, cols, figsize=(7.2, 2.3 * rows),
                                 sharex=True, squeeze=False)
        for ax, (cc, data) in zip(axes.flat, curves.items()):
            color = COUNTRY_COLORS.get(cc, INK2)
            ax.plot(grid, data["past"], color=MUTED, lw=1.4, ls=(0, (4, 3)))
            ax.plot(grid, data["today"], color=color, lw=2.0)
            ax.set_title(cc, color=color)
            ax.text(grid[-1], data["today"][-1], " today", color=color,
                    fontsize=7.5, va="center")
            ax.text(grid[-1], data["past"][-1], " 6m ago", color=MUTED,
                    fontsize=7.5, va="center")
        for ax in axes.flat[len(curves):]:
            ax.set_visible(False)
        for ax in axes[-1]:
            ax.set_xlabel("tenor, years")
        for ax in axes[:, 0]:
            ax.set_ylabel("yield, % eff. annual")
        fig.suptitle("Fitted local curves: today vs 6 months ago",
                     fontweight="bold", fontsize=10.5, y=1.0)
        fig.tight_layout()
        return _save(fig, "fig1_curves")


def plot_z_vs_cuts(summary: pd.DataFrame) -> Path:
    """Chart 2 — slope z-score vs cuts priced, one labeled point per trade."""
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(4.8, 4.0))
        ax.axhline(0, color=BASELINE, lw=0.8, zorder=1)
        ax.axvline(0, color=BASELINE, lw=0.8, zorder=1)
        for _, row in summary.iterrows():
            color = COUNTRY_COLORS.get(row["country"], INK2)
            ax.scatter(row["cuts_priced_12m_bp"], row["slope_z"], s=42,
                       color=color, zorder=3)
            ax.annotate(f'{row["country"]} {row["trade"]}',
                        (row["cuts_priced_12m_bp"], row["slope_z"]),
                        xytext=(5, 4), textcoords="offset points",
                        fontsize=8, color=INK)
        ax.set_xlabel("policy change priced over 12m, bp (negative = cuts)")
        ax.set_ylabel("slope z-score vs 5y history")
        ax.set_title("Rich cuts, flat curves — where both line up")
        fig.tight_layout()
        return _save(fig, "fig2_z_vs_cuts")


def plot_carry_ranking(summary: pd.DataFrame) -> Path:
    """Chart 3 — carry+rolldown per unit of vol, all trades ranked.

    Shows each trade in its positive-carry direction (steepener or
    flattener), so the ranking answers 'which trade pays best per unit of
    risk' directly.
    """
    frame = summary.copy()
    frame["direction"] = np.where(frame["carry_per_vol"] >= 0, "steepener", "flattener")
    frame["ratio"] = frame["carry_per_vol"].abs()
    frame["label"] = frame["country"] + " " + frame["trade"] + " " + frame["direction"]
    frame = frame.sort_values("ratio")
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(7.2, 0.42 * len(frame) + 1.2))
        colors = [COUNTRY_COLORS.get(cc, INK2) for cc in frame["country"]]
        bars = ax.barh(frame["label"], frame["ratio"], color=colors, height=0.62)
        for bar, ratio in zip(bars, frame["ratio"]):
            ax.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height() / 2,
                    f"{ratio:.2f}", va="center", fontsize=8, color=INK2)
        ax.grid(axis="y", visible=False)
        ax.set_xlabel("3m carry + rolldown per unit of 3m trade vol")
        ax.set_title("Carry per unit of risk, best direction per trade")
        fig.tight_layout()
        return _save(fig, "fig3_carry_per_vol")
