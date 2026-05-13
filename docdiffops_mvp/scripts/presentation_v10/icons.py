"""8 section icons rendered as PNG via matplotlib path patches.

Each icon is a flat line-art silhouette in OCEAN['accent'] (#21295C) on a
transparent background, 96×96 px.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, Rectangle
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch

from .theme import OCEAN

# Output directory: migration_v10_out/presentation/assets/
ICONS_DIR = Path(__file__).resolve().parents[3] / "migration_v10_out/presentation/assets"

_ACCENT = "#" + OCEAN["accent"]  # #21295C midnight blue
_LW = 7  # default line-width for stroked icons


def _new_icon_fig() -> tuple[plt.Figure, plt.Axes]:
    """Create a 1×1 inch figure for a single icon."""
    fig, ax = plt.subplots(figsize=(1, 1))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.patch.set_alpha(0.0)
    return fig, ax


def _save_icon(fig: plt.Figure, name: str, out_dir: Path) -> Path:
    """Save figure as 96-dpi transparent PNG. Returns output path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"icon_{name}.png"
    fig.savefig(str(out), dpi=96, transparent=True, bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# Individual icon functions
# ---------------------------------------------------------------------------


def icon_executive(out_dir: Path = ICONS_DIR) -> Path:
    """Trending-up arrow for Executive Summary."""
    fig, ax = _new_icon_fig()
    # Upward trend line
    xs = [0.1, 0.35, 0.5, 0.65, 0.82]
    ys = [0.18, 0.42, 0.35, 0.60, 0.82]
    ax.plot(xs, ys, color=_ACCENT, linewidth=_LW, solid_capstyle="round",
            solid_joinstyle="round")
    # Arrowhead at end
    ax.annotate(
        "",
        xy=(0.90, 0.88),
        xytext=(0.82, 0.82),
        arrowprops=dict(arrowstyle="-|>", color=_ACCENT, lw=_LW * 0.5,
                        mutation_scale=20),
    )
    return _save_icon(fig, "executive", out_dir)


def icon_corpus(out_dir: Path = ICONS_DIR) -> Path:
    """Book-stack icon for Корпус section — 3 layered rectangles."""
    fig, ax = _new_icon_fig()
    colors = [_ACCENT] * 3
    # Bottom book (widest)
    for i, (yb, h, xm) in enumerate([(0.10, 0.20, 0.05), (0.34, 0.18, 0.12), (0.56, 0.18, 0.18)]):
        lw = _LW if i < 2 else _LW
        rect = Rectangle((xm, yb), 1 - 2 * xm, h,
                          linewidth=lw, edgecolor=colors[i],
                          facecolor="none", capstyle="round", joinstyle="round")
        ax.add_patch(rect)
        # Spine line
        ax.plot([xm + 0.07, xm + 0.07], [yb + 0.04, yb + h - 0.04],
                color=_ACCENT, linewidth=max(2, _LW - 3))
    return _save_icon(fig, "corpus", out_dir)


def icon_pair_matrix(out_dir: Path = ICONS_DIR) -> Path:
    """3×3 grid icon for Pair Matrix section."""
    fig, ax = _new_icon_fig()
    margin = 0.12
    cell = (1 - 2 * margin) / 3
    gap = 0.04
    for row in range(3):
        for col in range(3):
            x = margin + col * (cell + gap)
            y = margin + row * (cell + gap)
            rect = Rectangle((x, y), cell - gap, cell - gap,
                              linewidth=_LW - 2, edgecolor=_ACCENT,
                              facecolor="none")
            ax.add_patch(rect)
    return _save_icon(fig, "pair_matrix", out_dir)


def icon_events(out_dir: Path = ICONS_DIR) -> Path:
    """Alert diamond + exclamation mark for Events section."""
    fig, ax = _new_icon_fig()
    # Diamond
    diamond_verts = [(0.5, 0.85), (0.87, 0.50), (0.5, 0.15), (0.13, 0.50), (0.5, 0.85)]
    xs, ys = zip(*diamond_verts)
    ax.plot(xs, ys, color=_ACCENT, linewidth=_LW,
            solid_capstyle="round", solid_joinstyle="round")
    # Exclamation body
    ax.plot([0.5, 0.5], [0.40, 0.65], color=_ACCENT, linewidth=_LW,
            solid_capstyle="round")
    # Exclamation dot
    dot = Circle((0.5, 0.28), 0.04, color=_ACCENT)
    ax.add_patch(dot)
    return _save_icon(fig, "events", out_dir)


def icon_themes(out_dir: Path = ICONS_DIR) -> Path:
    """Network/graph icon for Themes section — nodes + edges."""
    fig, ax = _new_icon_fig()
    # Node positions
    nodes = [(0.5, 0.75), (0.2, 0.35), (0.8, 0.35), (0.5, 0.15)]
    # Edges: center → each outer, outer nodes to bottom
    edges = [(0, 1), (0, 2), (1, 3), (2, 3), (1, 2)]
    for a, b in edges:
        ax.plot([nodes[a][0], nodes[b][0]], [nodes[a][1], nodes[b][1]],
                color=_ACCENT, linewidth=max(2, _LW - 3), zorder=1)
    # Draw nodes
    for x, y in nodes:
        c = Circle((x, y), 0.07, color=_ACCENT, zorder=2)
        ax.add_patch(c)
    return _save_icon(fig, "themes", out_dir)


def icon_review(out_dir: Path = ICONS_DIR) -> Path:
    """Clipboard-check icon for Review queue section."""
    fig, ax = _new_icon_fig()
    # Clipboard body
    rect = Rectangle((0.18, 0.08), 0.64, 0.76, linewidth=_LW,
                      edgecolor=_ACCENT, facecolor="none",
                      capstyle="round", joinstyle="round")
    ax.add_patch(rect)
    # Clip at top
    clip = Rectangle((0.36, 0.78), 0.28, 0.14, linewidth=_LW - 2,
                      edgecolor=_ACCENT, facecolor="none",
                      capstyle="round")
    ax.add_patch(clip)
    # Check mark
    ax.plot([0.28, 0.45, 0.72], [0.40, 0.25, 0.60],
            color=_ACCENT, linewidth=_LW, solid_capstyle="round",
            solid_joinstyle="round")
    return _save_icon(fig, "review", out_dir)


def icon_trend(out_dir: Path = ICONS_DIR) -> Path:
    """Line-chart icon for Trend section — axes + rising line."""
    fig, ax = _new_icon_fig()
    # Axes
    ax.plot([0.12, 0.12], [0.85, 0.12], color=_ACCENT, linewidth=_LW,
            solid_capstyle="round")  # Y-axis
    ax.plot([0.12, 0.88], [0.12, 0.12], color=_ACCENT, linewidth=_LW,
            solid_capstyle="round")  # X-axis
    # Trend line (rising)
    ax.plot([0.22, 0.40, 0.55, 0.70, 0.82],
            [0.22, 0.32, 0.45, 0.58, 0.75],
            color=_ACCENT, linewidth=_LW - 1, solid_capstyle="round",
            solid_joinstyle="round")
    # Arrow tip on Y axis
    ax.annotate("", xy=(0.12, 0.88), xytext=(0.12, 0.80),
                arrowprops=dict(arrowstyle="-|>", color=_ACCENT, lw=2,
                                mutation_scale=12))
    # Arrow tip on X axis
    ax.annotate("", xy=(0.91, 0.12), xytext=(0.83, 0.12),
                arrowprops=dict(arrowstyle="-|>", color=_ACCENT, lw=2,
                                mutation_scale=12))
    return _save_icon(fig, "trend", out_dir)


def icon_actions(out_dir: Path = ICONS_DIR) -> Path:
    """Lightning-bolt icon for Actions section — zigzag bolt."""
    fig, ax = _new_icon_fig()
    # Lightning bolt vertices
    bolt = [(0.58, 0.90), (0.32, 0.52), (0.50, 0.52), (0.28, 0.10),
            (0.62, 0.48), (0.44, 0.48), (0.58, 0.90)]
    xs, ys = zip(*bolt)
    ax.plot(xs, ys, color=_ACCENT, linewidth=_LW - 1,
            solid_capstyle="round", solid_joinstyle="round")
    ax.fill(xs, ys, color=_ACCENT, alpha=0.85)
    return _save_icon(fig, "actions", out_dir)


# ---------------------------------------------------------------------------
# Batch builder
# ---------------------------------------------------------------------------


def build_all_icons(out_dir: Path | str | None = None) -> dict[str, Path]:
    """Generate all 8 section icons. Returns mapping name → path."""
    d = ICONS_DIR if out_dir is None else Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    return {
        "executive":   icon_executive(d),
        "corpus":      icon_corpus(d),
        "pair_matrix": icon_pair_matrix(d),
        "events":      icon_events(d),
        "themes":      icon_themes(d),
        "review":      icon_review(d),
        "trend":       icon_trend(d),
        "actions":     icon_actions(d),
    }


if __name__ == "__main__":
    for name, p in build_all_icons().items():
        size_kb = p.stat().st_size // 1024
        print(f"  icon_{name}: {p} ({size_kb} KB)")
