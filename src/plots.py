"""Figure factory: three charts, one palette, exported as vector PDF.

Colours follow the entity: each country keeps one hue across all figures
(anchors muted grey so the EM story carries the colour). Figures carry no
in-image title — the document caption states the takeaway — and use direct
labels, never a legend box. Every function takes an exact output width so
each document embeds figures at 1:1 with no post-scaling (see src/theme.py).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src import theme

FIG_DIR = Path(__file__).resolve().parent.parent / "output" / "figs"


def _labels_no_overlap(ax, points: list[tuple[float, float, str, str]]) -> None:
    """Place point labels, nudging each to the first offset that clears the rest."""
    xr = max(np.ptp([p[0] for p in points]), 1e-9)
    yr = max(np.ptp([p[1] for p in points]), 1e-9)
    offsets = ((7, 3), (7, -10), (-7, 3), (-7, -10), (7, 13), (-7, 13))
    placed: list[tuple[float, float]] = []
    for x, y, text, color in points:
        for dx, dy in offsets:
            lx, ly = x + dx * xr / 300, y + dy * yr / 300
            if all(abs(lx - px) / xr > 0.15 or abs(ly - py) / yr > 0.05
                   for px, py in placed):
                break
        placed.append((lx, ly))
        ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points",
                    fontsize=8, color=theme.INK, ha="left" if dx > 0 else "right")


def plot_curve_panels(curves: dict[str, dict[str, np.ndarray]],
                      width_in: float = theme.NOTE_TEXT_IN,
                      fig_dir: Path | None = None) -> Path:
    """Fitted curve today vs 6m ago, one panel per country (shared x-axis).

    `curves[cc]` holds arrays 'today' and 'past' on its own 'grid' (years),
    so no panel extrapolates below its shortest observed tenor.
    """
    cols = min(len(curves), 4)
    rows = -(-len(curves) // cols)
    theme.apply()
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(rows, cols, figsize=(width_in, 2.25 * rows),
                             sharex=True, squeeze=False)
    for ax, (cc, data) in zip(axes.flat, curves.items()):
        color = theme.COUNTRY_COLORS.get(cc, theme.INK2)
        grid = data["grid"]
        ax.plot(grid, data["past"], color=theme.MUTED, lw=1.3, ls=(0, (4, 3)))
        ax.plot(grid, data["today"], color=color, lw=1.9)
        ax.set_title(cc, color=color, fontweight="bold", loc="left")
        span = max(np.ptp(np.r_[data["today"], data["past"]]), 1e-9)
        apart = data["today"][-1] - data["past"][-1]
        close = abs(apart) < 0.14 * span
        top = "bottom" if apart >= 0 else "top"
        ax.text(grid[-1], data["today"][-1], " now", color=color, fontsize=7.5,
                va=top if close else "center")
        ax.text(grid[-1], data["past"][-1], " 6m", color=theme.MUTED, fontsize=7.5,
                va=("top" if top == "bottom" else "bottom") if close else "center")
    for ax in axes.flat[len(curves):]:
        ax.set_visible(False)
    for ax in axes[-1]:
        ax.set_xlabel("tenor, years")
    axes[0, 0].set_ylabel("yield, % eff. annual")
    fig.tight_layout(pad=0.4, w_pad=1.0)
    fig.subplots_adjust(bottom=0.28)
    return theme.save(fig, (fig_dir or FIG_DIR) / "fig_curves.pdf")


def plot_z_vs_cuts(summary: pd.DataFrame, width_in: float = 3.95,
                   fig_dir: Path | None = None) -> Path:
    """Slope z-score vs policy change priced over 12m, one point per trade."""
    fig, ax = theme.figure(width_in, width_in * 0.92)
    ax.axhline(0, color=theme.BASELINE, lw=0.7, zorder=1)
    ax.axvline(0, color=theme.BASELINE, lw=0.7, zorder=1)
    pts = []
    for _, r in summary.iterrows():
        color = theme.COUNTRY_COLORS.get(r["country"], theme.INK2)
        ax.scatter(r["path_12m_bp"], r["slope_z"], s=40, color=color, zorder=3)
        pts.append((r["path_12m_bp"], r["slope_z"], f'{r["country"]} {r["trade"]}', color))
    _labels_no_overlap(ax, pts)
    ax.set_xlabel("policy change priced over 12m, bp\n(3m rate 9m fwd − policy; < 0 = cuts)")
    ax.set_ylabel("5s10s / 2s10s slope, z-score vs 5y history")
    fig.tight_layout(pad=0.5)
    fig.subplots_adjust(bottom=0.25)
    return theme.save(fig, (fig_dir or FIG_DIR) / "fig_z_vs_cuts.pdf")


def plot_carry_ranking(summary: pd.DataFrame, width_in: float = theme.NOTE_TEXT_IN,
                       fig_dir: Path | None = None) -> Path:
    """Carry + rolldown per unit of vol, each trade in its positive-carry direction."""
    frame = summary.copy()
    frame["direction"] = np.where(frame["carry_per_vol"] >= 0, "steepener", "flattener")
    frame["ratio"] = frame["carry_per_vol"].abs()
    frame["label"] = frame["country"] + " " + frame["trade"] + " " + frame["direction"]
    frame = frame.sort_values("ratio")
    fig, ax = theme.figure(width_in, 0.28 * len(frame) + 0.75)
    colors = [theme.COUNTRY_COLORS.get(cc, theme.INK2) for cc in frame["country"]]
    bars = ax.barh(frame["label"], frame["ratio"], color=colors, height=0.6)
    for bar, ratio in zip(bars, frame["ratio"]):
        ax.text(bar.get_width() + 0.004, bar.get_y() + bar.get_height() / 2,
                f"{ratio:.2f}", va="center", fontsize=8, color=theme.INK2)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("3m carry + rolldown per unit of 3m trade vol")
    ax.margins(x=0.10)
    fig.tight_layout(pad=0.5)
    fig.subplots_adjust(bottom=0.16)
    return theme.save(fig, (fig_dir or FIG_DIR) / "fig_carry_per_vol.pdf")
