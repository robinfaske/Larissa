"""Shared figure theme: STIX Two Text at document sizes, vector PDF export.

Both PDFs (report/ note and paper/) embed figures produced here, so the
in-figure typeface, sizes, and palette match the surrounding body text.
Figures are exported at exact text/column width as vector PDF — no
post-scaling in the document, no rasterized text.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
from matplotlib import font_manager

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FAMILY = "STIX Two Text"

# Column geometry (inches) matching the documents' text measures.
NOTE_TEXT_IN = 6.61   # A4 with 1.7cm side margins
PAPER_TEXT_IN = 6.55  # A4 with 2.2cm side margins
PAPER_FIG_IN = 3.5    # single academic figure, centered

INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE, SURFACE = "#e1e0d9", "#c3c2b7", "#ffffff"
COUNTRY_COLORS = {
    "MX": "#2a78d6", "BR": "#eb6834", "PL": "#1baf7a", "HU": "#eda100",
    "TR": "#e87ba4", "US": "#898781", "DE": "#b0aea6",
}
SOURCE_LINE = ("Source: Banxico SIE, Tesouro Direto, US Treasury, Bundesbank; "
               "author's calculations.")

_REGISTERED = False


def _register_fonts() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    for ttf in FONT_DIR.glob("*.ttf"):
        font_manager.fontManager.addfont(str(ttf))
    _REGISTERED = True


def apply() -> None:
    """Install the shared rcParams (idempotent)."""
    _register_fonts()
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE, "svg.fonttype": "none",
        "pdf.fonttype": 42, "ps.fonttype": 42,
        "font.family": FAMILY, "mathtext.fontset": "custom",
        "mathtext.rm": FAMILY, "mathtext.it": f"{FAMILY}:italic",
        "font.size": 9.0, "text.color": INK, "axes.labelcolor": INK2,
        "axes.edgecolor": BASELINE, "axes.linewidth": 0.7,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5,
        "xtick.color": MUTED, "ytick.color": MUTED,
        "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
        "axes.labelsize": 9.0, "axes.titlesize": 9.5,
        "legend.frameon": False, "legend.fontsize": 8.5,
        "axes.titlepad": 4.0, "lines.solid_capstyle": "round",
    })


def figure(width_in: float, height_in: float) -> tuple[plt.Figure, object]:
    """A themed figure sized to an exact document measure."""
    apply()
    return plt.subplots(figsize=(width_in, height_in))


def save(fig: plt.Figure, path: Path, source: bool = True) -> Path:
    """Write a vector PDF at the figure's exact size, with a source footnote.

    No bbox_inches='tight' — that would rescale text away from the document
    sizes; the caller sets a layout that already fits.
    """
    if source:
        fig.text(0.0, 0.005, SOURCE_LINE, fontsize=6.5, color=MUTED,
                 ha="left", va="bottom", style="italic")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="pdf")
    plt.close(fig)
    return path
