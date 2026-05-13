"""Generate all 10 PNG charts for the DocDiffOps v10 presentation.

Usage:
    cd docdiffops_mvp
    python -m scripts.presentation_v10.charts

All charts are written to ``migration_v10_out/presentation/assets/`` by default.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
import numpy as np
from pathlib import Path
from typing import Any

matplotlib.rcParams["font.family"] = "DejaVu Sans"
matplotlib.rcParams["axes.unicode_minus"] = False
matplotlib.rcParams["figure.dpi"] = 100

from .theme import (
    OCEAN,
    STATUS_HEX,
    STATUS_RU,
    V8_STATUSES,
    FONT_HEADER,
)
from .data_loader import V10Data, load_data

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = REPO_ROOT / "migration_v10_out" / "presentation" / "assets"


def _hex(h: str) -> str:
    """Ensure hex color has leading '#'."""
    return f"#{h}" if not h.startswith("#") else h


def _status_colors() -> dict[str, str]:
    return {s: _hex(STATUS_HEX[s]) for s in V8_STATUSES}


# ---------------------------------------------------------------------------
# 1. Status pie — pair-level
# ---------------------------------------------------------------------------

def chart_status_pie(data: V10Data, out_dir: Path) -> Path:
    """Pie chart of pair-level status distribution."""
    dist = data.pairs_by_status()
    labels = []
    sizes = []
    colors = []
    sc = _status_colors()

    for s in V8_STATUSES:
        n = dist.get(s, 0)
        if n > 0:
            labels.append(s)
            sizes.append(n)
            colors.append(sc[s])

    total = sum(sizes)
    fig, ax = plt.subplots(figsize=(19.2, 10.8))
    fig.patch.set_facecolor(_hex(OCEAN["bg_light"]))
    ax.set_facecolor(_hex(OCEAN["bg_light"]))

    def autopct_fn(pct: float) -> str:
        n = int(round(pct * total / 100))
        return f"{n}\n({pct:.1f}%)"

    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=None,
        colors=colors,
        autopct=autopct_fn,
        startangle=140,
        pctdistance=0.75,
        wedgeprops={"linewidth": 1.5, "edgecolor": "white"},
    )
    for at in autotexts:
        at.set_fontsize(11)
        at.set_color("white")
        at.set_fontweight("bold")

    # Legend with Russian labels
    legend_labels = [f"{STATUS_RU.get(s, s)}  ({dist.get(s, 0)})" for s in V8_STATUSES if dist.get(s, 0) > 0]
    ax.legend(
        handles=[mpatches.Patch(color=sc[s], label=legend_labels[i])
                 for i, s in enumerate(s_ for s_ in V8_STATUSES if dist.get(s_, 0) > 0)],
        loc="center left",
        bbox_to_anchor=(0.85, 0.5),
        fontsize=13,
        framealpha=0.9,
    )

    path = out_dir / "chart_status_pie.png"
    fig.savefig(path, bbox_inches="tight", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# 2. Trend — match share line chart
# ---------------------------------------------------------------------------

def chart_trend_match_share(data: V10Data, out_dir: Path) -> Path:
    """Line chart of match_share across versions v7..v10."""
    timeline = data.trend.get("timeline", [])
    versions = [t["version"] for t in timeline]
    match_shares = [float(t.get("match_share", 0)) for t in timeline]

    fig, ax = plt.subplots(figsize=(19.2, 9.0))
    fig.patch.set_facecolor(_hex(OCEAN["bg_light"]))
    ax.set_facecolor(_hex(OCEAN["bg_light"]))

    color = _hex(OCEAN["primary"])
    ax.plot(versions, match_shares, color=color, linewidth=3, marker="o", markersize=12,
            markerfacecolor=color, markeredgecolor="white", markeredgewidth=2, zorder=5)

    # Annotate each point
    for i, (v, val) in enumerate(zip(versions, match_shares)):
        ax.annotate(
            f"{val:.2f}%",
            xy=(i, val),
            xytext=(0, 20),
            textcoords="offset points",
            ha="center",
            fontsize=13,
            fontweight="bold",
            color=color,
        )

    ax.set_xticks(range(len(versions)))
    ax.set_xticklabels(versions, fontsize=14)
    ax.set_ylabel("match_share, %", fontsize=13, color=_hex(OCEAN["ink"]))
    ax.tick_params(colors=_hex(OCEAN["ink"]))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color(_hex(OCEAN["rule"]))
    ax.yaxis.grid(True, color=_hex(OCEAN["rule"]), linewidth=0.8, alpha=0.7)
    ax.set_axisbelow(True)

    fig.text(
        0.5, 0.01,
        "v8→v9: драматический спад связан с расширением корпуса (12→27 документов, 78→351 пара)",
        ha="center",
        fontsize=11,
        color=_hex(OCEAN["muted"]),
        style="italic",
    )

    path = out_dir / "chart_trend_match_share.png"
    fig.savefig(path, bbox_inches="tight", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# 3. Trend — review queue bar chart
# ---------------------------------------------------------------------------

def chart_trend_review_queue(data: V10Data, out_dir: Path) -> Path:
    """Bar chart of review_queue size across versions."""
    timeline = data.trend.get("timeline", [])
    versions = [t["version"] for t in timeline]
    review_sizes = [int(t.get("review_queue", 0)) for t in timeline]

    fig, ax = plt.subplots(figsize=(19.2, 9.0))
    fig.patch.set_facecolor(_hex(OCEAN["bg_light"]))
    ax.set_facecolor(_hex(OCEAN["bg_light"]))

    color = _hex(OCEAN["secondary"])
    bars = ax.bar(versions, review_sizes, color=color, width=0.5,
                  edgecolor="white", linewidth=1.5, zorder=3)

    for bar, val in zip(bars, review_sizes):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(review_sizes) * 0.02,
            str(val),
            ha="center",
            va="bottom",
            fontsize=14,
            fontweight="bold",
            color=_hex(OCEAN["ink"]),
        )

    ax.set_ylabel("Размер очереди", fontsize=13, color=_hex(OCEAN["ink"]))
    ax.tick_params(colors=_hex(OCEAN["ink"]), labelsize=13)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color(_hex(OCEAN["rule"]))
    ax.yaxis.grid(True, color=_hex(OCEAN["rule"]), linewidth=0.8, alpha=0.7)
    ax.set_axisbelow(True)

    path = out_dir / "chart_trend_review_queue.png"
    fig.savefig(path, bbox_inches="tight", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# 4. Rank distribution — stacked horizontal bar
# ---------------------------------------------------------------------------

def chart_rank_distribution(data: V10Data, out_dir: Path) -> Path:
    """Stacked horizontal bar chart: status distribution per rank_pair."""
    sc = _status_colors()
    rank_pairs_order = ["1↔1", "1↔2", "1↔3", "2↔2", "2↔3", "3↔3"]

    # Count (rank_pair, v8_status)
    counts: dict[str, dict[str, int]] = {rp: {s: 0 for s in V8_STATUSES} for rp in rank_pairs_order}
    for p in data.pairs:
        rp = p.get("rank_pair", "").strip()
        s = p.get("v8_status", "").strip()
        if rp in counts and s in counts[rp]:
            counts[rp][s] += 1

    fig, ax = plt.subplots(figsize=(19.2, 9.0))
    fig.patch.set_facecolor(_hex(OCEAN["bg_light"]))
    ax.set_facecolor(_hex(OCEAN["bg_light"]))

    y_pos = np.arange(len(rank_pairs_order))
    lefts = np.zeros(len(rank_pairs_order))

    for status in V8_STATUSES:
        vals = np.array([counts[rp][status] for rp in rank_pairs_order], dtype=float)
        if vals.sum() == 0:
            continue
        bars = ax.barh(y_pos, vals, left=lefts, color=sc[status], label=STATUS_RU.get(status, status),
                       edgecolor="white", linewidth=0.8, height=0.6)
        # Label bars with count if wide enough
        for bar, val, left in zip(bars, vals, lefts):
            if val >= 3:
                ax.text(
                    left + val / 2,
                    bar.get_y() + bar.get_height() / 2,
                    str(int(val)),
                    ha="center",
                    va="center",
                    fontsize=10,
                    fontweight="bold",
                    color="white",
                )
        lefts += vals

    ax.set_yticks(y_pos)
    ax.set_yticklabels(rank_pairs_order, fontsize=14)
    ax.set_xlabel("Число пар", fontsize=13, color=_hex(OCEAN["ink"]))
    ax.tick_params(colors=_hex(OCEAN["ink"]))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color(_hex(OCEAN["rule"]))
    ax.xaxis.grid(True, color=_hex(OCEAN["rule"]), linewidth=0.8, alpha=0.7)
    ax.set_axisbelow(True)

    ax.legend(
        loc="lower right",
        fontsize=11,
        framealpha=0.9,
        ncol=2,
    )

    path = out_dir / "chart_rank_distribution.png"
    fig.savefig(path, bbox_inches="tight", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# 5. Correlation heatmap — themes × documents (binary)
# ---------------------------------------------------------------------------

def chart_correlation_heatmap(data: V10Data, out_dir: Path) -> Path:
    """Binary heatmap: 14 themes × 27 documents."""
    matrix_rows = data.correlation_matrix
    doc_cols = [f"D{i:02d}" for i in range(1, 28)]
    theme_names = [r.get("theme_name", r.get("theme_id", "")) for r in matrix_rows]

    matrix = np.zeros((len(matrix_rows), len(doc_cols)), dtype=float)
    for i, row in enumerate(matrix_rows):
        for j, col in enumerate(doc_cols):
            val = row.get(col, "0").strip()
            try:
                matrix[i, j] = float(val)
            except ValueError:
                matrix[i, j] = 0.0

    fig, ax = plt.subplots(figsize=(19.2, 10.8))
    fig.patch.set_facecolor(_hex(OCEAN["bg_light"]))
    ax.set_facecolor(_hex(OCEAN["bg_light"]))

    # Discrete colormap: bg_light (0) → primary (1)
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "ocean_binary",
        [_hex(OCEAN["bg_light"]), _hex(OCEAN["primary"])],
        N=2,
    )
    im = ax.imshow(matrix, cmap=cmap, aspect="auto", vmin=0, vmax=1)

    ax.set_xticks(range(len(doc_cols)))
    ax.set_xticklabels(doc_cols, rotation=45, ha="right", fontsize=10)
    ax.set_yticks(range(len(theme_names)))
    ax.set_yticklabels(theme_names, fontsize=10)
    ax.tick_params(colors=_hex(OCEAN["ink"]))

    # Gridlines
    ax.set_xticks(np.arange(-0.5, len(doc_cols), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(matrix_rows), 1), minor=True)
    ax.grid(which="minor", color=_hex(OCEAN["rule"]), linewidth=0.5)
    ax.tick_params(which="minor", length=0)

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, shrink=0.6, pad=0.02)
    cbar.set_ticks([0.25, 0.75])
    cbar.set_ticklabels(["0", "1"])
    cbar.ax.tick_params(labelsize=10)

    fig.tight_layout()
    fig.subplots_adjust(left=0.18, right=0.88, top=0.92, bottom=0.18)
    path = out_dir / "chart_correlation_heatmap.png"
    fig.savefig(path, bbox_inches="tight", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# 6. Coverage heatmap — themes × rank coverage (gradient)
# ---------------------------------------------------------------------------

def chart_coverage_heatmap(data: V10Data, out_dir: Path) -> Path:
    """Coverage depth heatmap using rank coverage columns."""
    # coverage_heatmap.csv has columns: theme_id, theme_name, rank_1..rank_4
    # We use rank_1..rank_3 as coverage depth per theme
    heatmap_rows = data.coverage_heatmap

    # If the file has rank_1..rank_4 columns (actual format)
    rank_cols = ["rank_1", "rank_2", "rank_3", "rank_4"]
    rank_labels = ["Ранг 1", "Ранг 2", "Ранг 3", "Ранг 4"]

    # Check if rank cols exist
    if heatmap_rows and "rank_1" in heatmap_rows[0]:
        theme_names = [r.get("theme_name", r.get("theme_id", "")) for r in heatmap_rows]
        matrix = np.zeros((len(heatmap_rows), len(rank_cols)), dtype=float)
        for i, row in enumerate(heatmap_rows):
            for j, col in enumerate(rank_cols):
                try:
                    matrix[i, j] = float(row.get(col, "0") or "0")
                except ValueError:
                    matrix[i, j] = 0.0
        col_labels = rank_labels
    else:
        # Fallback: use correlation_matrix D01..D27 with float values
        doc_cols = [f"D{i:02d}" for i in range(1, 28)]
        theme_names = [r.get("theme_name", r.get("theme_id", "")) for r in heatmap_rows]
        matrix = np.zeros((len(heatmap_rows), len(doc_cols)), dtype=float)
        for i, row in enumerate(heatmap_rows):
            for j, col in enumerate(doc_cols):
                try:
                    matrix[i, j] = float(row.get(col, "0") or "0")
                except ValueError:
                    matrix[i, j] = 0.0
        col_labels = doc_cols

    fig, ax = plt.subplots(figsize=(19.2, 10.8))
    fig.patch.set_facecolor(_hex(OCEAN["bg_light"]))
    ax.set_facecolor(_hex(OCEAN["bg_light"]))

    cmap = mcolors.LinearSegmentedColormap.from_list(
        "ocean_coverage",
        [_hex(OCEAN["bg_light"]), _hex(OCEAN["secondary"]), _hex(OCEAN["primary"])],
        N=256,
    )
    vmax = max(matrix.max(), 1.0)
    im = ax.imshow(matrix, cmap=cmap, aspect="auto", vmin=0, vmax=vmax)

    ax.set_xticks(range(len(col_labels)))
    ax.set_xticklabels(col_labels, rotation=0 if len(col_labels) <= 6 else 45,
                       ha="right", fontsize=12 if len(col_labels) <= 6 else 10)
    ax.set_yticks(range(len(theme_names)))
    ax.set_yticklabels(theme_names, fontsize=10)
    ax.tick_params(colors=_hex(OCEAN["ink"]))

    # Annotate cells with values
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            val = matrix[i, j]
            if val > 0:
                text_color = "white" if val > vmax * 0.5 else _hex(OCEAN["ink"])
                ax.text(j, i, str(int(val)), ha="center", va="center",
                        fontsize=10, fontweight="bold", color=text_color)

    # Minor grid
    ax.set_xticks(np.arange(-0.5, len(col_labels), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(theme_names), 1), minor=True)
    ax.grid(which="minor", color=_hex(OCEAN["rule"]), linewidth=0.5)
    ax.tick_params(which="minor", length=0)

    cbar = fig.colorbar(im, ax=ax, shrink=0.6, pad=0.02)
    cbar.ax.tick_params(labelsize=10)

    fig.tight_layout()
    fig.subplots_adjust(left=0.18, right=0.88, top=0.92, bottom=0.18)
    path = out_dir / "chart_coverage_heatmap.png"
    fig.savefig(path, bbox_inches="tight", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# 7. Dependency graph — networkx + matplotlib
# ---------------------------------------------------------------------------

def chart_dependency_graph(data: V10Data, out_dir: Path) -> Path:
    """Directed dependency graph of documents."""
    import networkx as nx

    sc = _status_colors()
    rel_colors: dict[str, str] = {
        "amends":       sc.get("outdated", _hex(OCEAN["secondary"])),
        "amended_by":   sc.get("outdated", _hex(OCEAN["secondary"])),
        "supersedes":   sc.get("contradiction", "#DC2626"),
        "superseded_by": sc.get("contradiction", "#DC2626"),
        "references":   _hex(OCEAN["secondary"]),
    }

    # Build graph
    G = nx.DiGraph()
    docs_by_rank = data.docs_by_rank()

    # Add nodes
    for rank, docs in docs_by_rank.items():
        for doc in docs:
            doc_id = doc.get("id", "")
            code = (doc.get("code") or doc_id).strip()
            G.add_node(doc_id, rank=rank, label=doc_id, code=code)

    # Add edges
    edge_colors_list: list[str] = []
    edge_list: list[tuple[str, str]] = []
    for edge in data.dependency_graph:
        src = edge.get("from_doc_id", "").strip()
        dst = edge.get("to_doc_id", "").strip()
        rel = edge.get("relation_type", "").strip()
        if src and dst:
            G.add_edge(src, dst, relation_type=rel)
            edge_list.append((src, dst))
            color = rel_colors.get(rel, _hex(OCEAN["muted"]))
            edge_colors_list.append(color)

    rank_node_colors: dict[int, str] = {
        1: _hex(OCEAN["primary"]),
        2: _hex(OCEAN["secondary"]),
        3: _hex(OCEAN["accent"]),
    }

    node_colors = []
    for node in G.nodes():
        r = G.nodes[node].get("rank", 0)
        node_colors.append(rank_node_colors.get(r, _hex(OCEAN["muted"])))

    fig, ax = plt.subplots(figsize=(24, 16))
    fig.patch.set_facecolor(_hex(OCEAN["bg_dark"]))
    ax.set_facecolor(_hex(OCEAN["bg_dark"]))

    try:
        pos = nx.kamada_kawai_layout(G)
    except Exception:
        pos = nx.spring_layout(G, seed=42, k=2.5)

    node_labels = {n: G.nodes[n].get("label", n) for n in G.nodes()}

    nx.draw_networkx_nodes(
        G, pos, ax=ax,
        node_color=node_colors,
        node_size=1200,
        alpha=0.95,
    )
    nx.draw_networkx_labels(
        G, pos, labels=node_labels, ax=ax,
        font_size=9,
        font_color="white",
        font_weight="bold",
    )
    if edge_list:
        nx.draw_networkx_edges(
            G, pos, edgelist=edge_list,
            edge_color=edge_colors_list,
            ax=ax,
            arrows=True,
            arrowsize=15,
            width=1.5,
            alpha=0.8,
            connectionstyle="arc3,rad=0.1",
        )

    # Legend
    legend_handles = [
        mpatches.Patch(color=rank_node_colors[1], label="Ранг 1 (НПА)"),
        mpatches.Patch(color=rank_node_colors[2], label="Ранг 2 (ведомственные)"),
        mpatches.Patch(color=rank_node_colors[3], label="Ранг 3 (аналитика)"),
        mpatches.Patch(color=rel_colors["amends"], label="amends/amended_by"),
        mpatches.Patch(color=rel_colors["supersedes"], label="supersedes/superseded_by"),
        mpatches.Patch(color=rel_colors["references"], label="references"),
        mpatches.Patch(color=_hex(OCEAN["muted"]), label="прочее"),
    ]
    ax.legend(
        handles=legend_handles,
        loc="upper left",
        fontsize=11,
        framealpha=0.85,
        facecolor=_hex(OCEAN["bg_dark"]),
        labelcolor="white",
    )

    ax.axis("off")

    path = out_dir / "chart_dependency_graph.png"
    fig.savefig(path, bbox_inches="tight", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# 8. Themes distribution — horizontal bar
# ---------------------------------------------------------------------------

def chart_themes_distribution(data: V10Data, out_dir: Path) -> Path:
    """Horizontal bar chart of events per theme (top-15)."""
    dist = data.themes_distribution()
    sorted_items = sorted(dist.items(), key=lambda x: x[1], reverse=True)[:15]
    themes = [item[0] for item in sorted_items]
    counts = [item[1] for item in sorted_items]

    # Truncate long theme names
    max_label = 45
    theme_labels = [t[:max_label] + "…" if len(t) > max_label else t for t in themes]

    fig, ax = plt.subplots(figsize=(19.2, 10.8))
    fig.patch.set_facecolor(_hex(OCEAN["bg_light"]))
    ax.set_facecolor(_hex(OCEAN["bg_light"]))

    y_pos = np.arange(len(themes))
    bars = ax.barh(
        y_pos[::-1],  # top to bottom = most popular first
        counts,
        color=_hex(OCEAN["primary"]),
        edgecolor="white",
        linewidth=0.8,
        height=0.65,
    )

    for bar, val in zip(bars, counts):
        ax.text(
            bar.get_width() + max(counts) * 0.01,
            bar.get_y() + bar.get_height() / 2,
            str(val),
            va="center",
            fontsize=11,
            fontweight="bold",
            color=_hex(OCEAN["ink"]),
        )

    ax.set_yticks(y_pos[::-1])
    ax.set_yticklabels(theme_labels, fontsize=10)
    ax.set_xlabel("Число событий", fontsize=13, color=_hex(OCEAN["ink"]))
    ax.tick_params(colors=_hex(OCEAN["ink"]))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color(_hex(OCEAN["rule"]))
    ax.xaxis.grid(True, color=_hex(OCEAN["rule"]), linewidth=0.8, alpha=0.7)
    ax.set_axisbelow(True)

    fig.tight_layout()
    path = out_dir / "chart_themes_distribution.png"
    fig.savefig(path, bbox_inches="tight", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# 9. Priority split — donut chart
# ---------------------------------------------------------------------------

def chart_priority_split(data: V10Data, out_dir: Path) -> Path:
    """Donut chart of review queue by priority (P0/P1/P2)."""
    dist = data.review_by_priority()
    sc = _status_colors()

    priority_colors: dict[str, str] = {
        "P0": sc.get("contradiction", "#DC2626"),
        "P1": sc.get("manual_review", "#EA580C"),
        "P2": sc.get("outdated", "#2563EB"),
    }

    labels = sorted(dist.keys())
    sizes = [dist.get(p, 0) for p in labels]
    colors = [priority_colors.get(p, _hex(OCEAN["muted"])) for p in labels]
    total = sum(sizes)

    fig, ax = plt.subplots(figsize=(19.2, 9.0))
    fig.patch.set_facecolor(_hex(OCEAN["bg_light"]))
    ax.set_facecolor(_hex(OCEAN["bg_light"]))

    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=labels,
        colors=colors,
        autopct=lambda pct: f"{int(round(pct * total / 100))}\n({pct:.1f}%)",
        startangle=90,
        pctdistance=0.72,
        wedgeprops={"width": 0.55, "linewidth": 2, "edgecolor": "white"},
        textprops={"fontsize": 14, "fontweight": "bold", "color": _hex(OCEAN["ink"])},
    )
    for at in autotexts:
        at.set_fontsize(12)
        at.set_color("white")
        at.set_fontweight("bold")

    # Center text
    ax.text(
        0, 0,
        str(total),
        ha="center",
        va="center",
        fontsize=44,
        fontweight="bold",
        color=_hex(OCEAN["ink"]),
    )
    ax.text(
        0, -0.18,
        "задач",
        ha="center",
        va="center",
        fontsize=16,
        color=_hex(OCEAN["muted"]),
    )

    path = out_dir / "chart_priority_split.png"
    fig.savefig(path, bbox_inches="tight", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# 10. Actions by severity — bar chart
# ---------------------------------------------------------------------------

def chart_actions_severity(data: V10Data, out_dir: Path) -> Path:
    """Bar chart of actions by severity (high/medium/low)."""
    dist = data.actions_by_severity()
    sc = _status_colors()

    severity_colors: dict[str, str] = {
        "high":   sc.get("contradiction", "#DC2626"),
        "medium": sc.get("manual_review", "#EA580C"),
        "low":    sc.get("outdated", "#2563EB"),
    }

    order = ["high", "medium", "low"]
    labels_ru = {"high": "Высокая (high)", "medium": "Средняя (medium)", "low": "Низкая (low)"}
    present = [s for s in order if s in dist]
    values = [dist[s] for s in present]
    colors = [severity_colors.get(s, _hex(OCEAN["muted"])) for s in present]
    x_labels = [labels_ru.get(s, s) for s in present]

    fig, ax = plt.subplots(figsize=(19.2, 9.0))
    fig.patch.set_facecolor(_hex(OCEAN["bg_light"]))
    ax.set_facecolor(_hex(OCEAN["bg_light"]))

    bars = ax.bar(
        x_labels,
        values,
        color=colors,
        width=0.45,
        edgecolor="white",
        linewidth=1.5,
        zorder=3,
    )

    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.1,
            str(val),
            ha="center",
            va="bottom",
            fontsize=18,
            fontweight="bold",
            color=_hex(OCEAN["ink"]),
        )

    ax.set_ylabel("Число действий", fontsize=13, color=_hex(OCEAN["ink"]))
    ax.tick_params(colors=_hex(OCEAN["ink"]), labelsize=14)
    ax.set_ylim(0, max(values) * 1.2 if values else 5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color(_hex(OCEAN["rule"]))
    ax.yaxis.grid(True, color=_hex(OCEAN["rule"]), linewidth=0.8, alpha=0.7)
    ax.set_axisbelow(True)

    path = out_dir / "chart_actions_severity.png"
    fig.savefig(path, bbox_inches="tight", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# 11. Sankey rank flow — manual bezier implementation
# ---------------------------------------------------------------------------

def chart_sankey_rank_flow(data: V10Data, out_dir: Path) -> Path:
    """Sankey flow diagram: rank-pairs → v8 statuses (1920×1200)."""
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MPath

    rank_pairs_order = ["1↔1", "1↔2", "1↔3", "2↔2", "2↔3", "3↔3"]
    sc = _status_colors()

    # Aggregate counts (rank_pair, v8_status)
    counts: dict[str, dict[str, int]] = {
        rp: {s: 0 for s in V8_STATUSES} for rp in rank_pairs_order
    }
    for p in data.pairs:
        rp = p.get("rank_pair", "").strip()
        s = p.get("v8_status", "").strip()
        if rp in counts and s in counts[rp]:
            counts[rp][s] += 1

    fig, ax = plt.subplots(figsize=(19.2, 12.0))
    fig.patch.set_facecolor(_hex(OCEAN["bg_light"]))
    ax.set_facecolor(_hex(OCEAN["bg_light"]))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 1)
    ax.axis("off")

    left_x = 1.5
    right_x = 8.5
    pad = 0.015

    # Compute left column heights (rank_pair totals)
    left_totals = [sum(counts[rp].values()) for rp in rank_pairs_order]
    grand_total = max(sum(left_totals), 1)
    left_heights = [t / grand_total for t in left_totals]

    # Compute right column heights (status totals)
    status_totals = {s: sum(counts[rp][s] for rp in rank_pairs_order) for s in V8_STATUSES}
    right_heights = [status_totals[s] / grand_total for s in V8_STATUSES]

    # Layout left blocks (bottom to top, add gaps)
    left_blocks: dict[str, tuple[float, float]] = {}  # rp → (y_bottom, y_top)
    y = 0.05
    for rp, h in zip(rank_pairs_order, left_heights):
        left_blocks[rp] = (y, y + h * 0.90)
        y += h * 0.90 + pad

    # Layout right blocks
    right_blocks: dict[str, tuple[float, float]] = {}
    y = 0.05
    for s, h in zip(V8_STATUSES, right_heights):
        right_blocks[s] = (y, y + h * 0.90)
        y += h * 0.90 + pad

    # Draw flows using bezier curves
    left_cursors = {rp: left_blocks[rp][0] for rp in rank_pairs_order}
    right_cursors = {s: right_blocks[s][0] for s in V8_STATUSES}

    for rp in rank_pairs_order:
        for s in V8_STATUSES:
            n = counts[rp][s]
            if n == 0:
                continue
            flow_h = n / grand_total * 0.90

            ly0 = left_cursors[rp]
            ly1 = ly0 + flow_h
            ry0 = right_cursors[s]
            ry1 = ry0 + flow_h

            left_cursors[rp] = ly1
            right_cursors[s] = ry1

            # Bezier path: left edge (ly0→ly1) → right edge (ry1→ry0)
            ctrl_x = (left_x + right_x) / 2
            verts = [
                (left_x, ly0),
                (ctrl_x, ly0),
                (ctrl_x, ry0),
                (right_x, ry0),
                (right_x, ry1),
                (ctrl_x, ry1),
                (ctrl_x, ly1),
                (left_x, ly1),
                (left_x, ly0),
            ]
            codes = [
                MPath.MOVETO,
                MPath.CURVE4, MPath.CURVE4, MPath.CURVE4,
                MPath.LINETO,
                MPath.CURVE4, MPath.CURVE4, MPath.CURVE4,
                MPath.CLOSEPOLY,
            ]
            patch = PathPatch(
                MPath(verts, codes),
                facecolor=sc[s],
                alpha=0.55,
                edgecolor="none",
            )
            ax.add_patch(patch)

    # Draw left column blocks
    rp_colors = [
        _hex(OCEAN["primary"]),
        _hex(OCEAN["secondary"]),
        _hex(OCEAN["accent"]),
        _hex(OCEAN["muted"]),
        "#4B5563",
        "#9CA3AF",
    ]
    for i, rp in enumerate(rank_pairs_order):
        y0, y1 = left_blocks[rp]
        ax.add_patch(plt.Rectangle(
            (left_x - 0.18, y0), 0.18, y1 - y0,
            facecolor=rp_colors[i], edgecolor="white", linewidth=0.5,
        ))
        if y1 - y0 > 0.03:
            ax.text(
                left_x - 0.09, (y0 + y1) / 2, rp,
                ha="center", va="center", fontsize=9, fontweight="bold",
                color="white", rotation=90,
            )

    # Draw right column blocks
    for s in V8_STATUSES:
        y0, y1 = right_blocks[s]
        ax.add_patch(plt.Rectangle(
            (right_x, y0), 0.18, y1 - y0,
            facecolor=sc[s], edgecolor="white", linewidth=0.5,
        ))
        if y1 - y0 > 0.03:
            ax.text(
                right_x + 0.09, (y0 + y1) / 2,
                STATUS_RU.get(s, s),
                ha="center", va="center", fontsize=8, fontweight="bold",
                color="white", rotation=90,
            )

    # Column labels
    ax.text(left_x - 0.09, 0.97, "Ранг-пара", ha="center", va="top",
            fontsize=12, fontweight="bold", color=_hex(OCEAN["ink"]))
    ax.text(right_x + 0.09, 0.97, "Статус", ha="center", va="top",
            fontsize=12, fontweight="bold", color=_hex(OCEAN["ink"]))

    path = out_dir / "chart_sankey_rank_flow.png"
    fig.savefig(path, bbox_inches="tight", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# 12. Treemap — themes by event count
# ---------------------------------------------------------------------------

def chart_treemap_themes(data: V10Data, out_dir: Path) -> Path:
    """Treemap of themes by event count with dominant-status coloring (1920×1080)."""
    import squarify
    from collections import Counter

    # Build per-theme (count, dominant_status)
    theme_status: dict[str, list[str]] = {}
    for ev in data.events_all:
        t = (ev.get("theme") or "").strip() or "—"
        s = (ev.get("status") or "").strip()
        theme_status.setdefault(t, []).append(s)

    sc = _status_colors()
    items = sorted(theme_status.items(), key=lambda x: len(x[1]), reverse=True)[:14]

    sizes = [len(statuses) for _, statuses in items]
    labels = []
    colors = []
    for theme, statuses in items:
        dominant = Counter(statuses).most_common(1)[0][0] if statuses else "not_comparable"
        colors.append(sc.get(dominant, _hex(OCEAN["muted"])))
        short = theme[:30] + "…" if len(theme) > 30 else theme
        labels.append(f"{short}\n{len(statuses)}")

    fig, ax = plt.subplots(figsize=(19.2, 10.8))
    fig.patch.set_facecolor(_hex(OCEAN["bg_light"]))
    ax.set_facecolor(_hex(OCEAN["bg_light"]))

    squarify.plot(
        sizes=sizes,
        label=labels,
        color=colors,
        alpha=0.85,
        edgecolor="white",
        linewidth=2,
        text_kwargs={"fontsize": 10, "color": "white", "fontweight": "bold",
                     "wrap": True},
        ax=ax,
    )
    ax.set_axis_off()

    fig.tight_layout(pad=0.5)
    path = out_dir / "chart_treemap_themes.png"
    fig.savefig(path, bbox_inches="tight", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# 13. Journey timeline — v7→v8→v9→v10
# ---------------------------------------------------------------------------

def chart_journey_timeline(data: V10Data, out_dir: Path) -> Path:
    """Horizontal journey timeline v7→v10 (2400×900)."""
    fig, ax = plt.subplots(figsize=(24.0, 9.0))
    fig.patch.set_facecolor(_hex(OCEAN["bg_light"]))
    ax.set_facecolor(_hex(OCEAN["bg_light"]))

    versions = ["v7", "v8", "v9", "v10"]
    dates = ["2024-Q3", "2024-Q4", "2025-Q1", "2025-Q2"]
    docs_counts = [12, 12, 27, 27]
    pairs_counts = [66, 66, 351, 351]
    events_counts = [200, 280, 312, 312]

    x_pos = [2, 6, 10, 14]
    bronze = _hex(OCEAN["bronze"])
    primary = _hex(OCEAN["primary"])

    # Timeline spine
    ax.plot([x_pos[0], x_pos[-1]], [5, 5], color=bronze, linewidth=3, zorder=1)

    # Version circles sized by docs
    max_docs = max(docs_counts)
    for i, (x, ver, dt, docs, pairs, evts) in enumerate(
        zip(x_pos, versions, dates, docs_counts, pairs_counts, events_counts)
    ):
        radius = 0.5 + 1.2 * (docs / max_docs)
        circle = plt.Circle(
            (x, 5), radius,
            color=primary if ver != "v10" else bronze,
            zorder=3, alpha=0.9,
        )
        ax.add_patch(circle)
        ax.text(x, 5, ver, ha="center", va="center",
                fontsize=13, fontweight="bold", color="white", zorder=4)

        # Bubble above
        bubble_y = 5 + radius + 0.8
        info = f"{docs} doc\n{pairs} пар\n{evts} evt"
        ax.text(x, bubble_y, info, ha="center", va="bottom",
                fontsize=9, color=_hex(OCEAN["ink"]),
                bbox=dict(boxstyle="round,pad=0.3", facecolor=_hex(OCEAN["tile_bg"]),
                          edgecolor=_hex(OCEAN["rule"]), linewidth=0.8))

        # Date below
        ax.text(x, 5 - radius - 0.5, dt, ha="center", va="top",
                fontsize=9, color=_hex(OCEAN["muted"]))

    # Annotations between versions
    transitions = [
        (x_pos[0], x_pos[1], "v7→v8:\nrefinement"),
        (x_pos[1], x_pos[2], "v8→v9:\n+D27 ВЦИОМ\n(rank-3)"),
        (x_pos[2], x_pos[3], "v9→v10:\nрендеринг-\nрелиз"),
    ]
    for x0, x1, label in transitions:
        xm = (x0 + x1) / 2
        ax.annotate(
            label,
            xy=(xm, 5),
            xytext=(xm, 2.5),
            ha="center",
            va="top",
            fontsize=8,
            color=_hex(OCEAN["muted"]),
            arrowprops=dict(arrowstyle="-", color=_hex(OCEAN["rule"]), lw=0.8),
        )

    ax.set_xlim(0, 16)
    ax.set_ylim(0, 10)
    ax.axis("off")

    path = out_dir / "chart_journey_timeline.png"
    fig.savefig(path, bbox_inches="tight", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# 14. Hero visualization — cover/hero stat combo
# ---------------------------------------------------------------------------

def chart_hero_visualization(data: V10Data, out_dir: Path) -> Path:
    """Hero combo: large stat + ring + side labels (1920×1200)."""
    sc = _status_colors()
    dist = data.pairs_by_status()
    sizes = [dist.get(s, 0) for s in V8_STATUSES]
    colors = [sc[s] for s in V8_STATUSES]
    total_pairs = sum(sizes)
    total_docs = len(data.documents)
    total_events = len(data.events_all)

    fig, ax = plt.subplots(figsize=(19.2, 12.0))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")

    # Center ring (donut)
    cx, cy, ring_r = 5.0, 5.0, 2.2
    theta = 0.0
    for size, color in zip(sizes, colors):
        if size == 0:
            continue
        angle = 2 * np.pi * size / max(total_pairs, 1)
        wedge = mpatches.Wedge(
            (cx, cy), ring_r,
            np.degrees(theta), np.degrees(theta + angle),
            width=0.55,
            facecolor=color, edgecolor="white", linewidth=1.5,
        )
        ax.add_patch(wedge)
        theta += angle

    # Central large number
    ax.text(cx, cy + 0.3, str(total_pairs),
            ha="center", va="center",
            fontsize=72, fontweight="bold", color=_hex(OCEAN["primary"]))
    ax.text(cx, cy - 0.8, "пар сравнений",
            ha="center", va="center",
            fontsize=16, color=_hex(OCEAN["muted"]))

    # Left stat — docs
    ax.text(1.5, cy + 0.5, str(total_docs),
            ha="center", va="center",
            fontsize=36, fontweight="bold", color=_hex(OCEAN["bronze"]))
    ax.text(1.5, cy - 0.3, "документов",
            ha="center", va="center",
            fontsize=13, color=_hex(OCEAN["muted"]))
    dot_l = plt.Circle((1.5, cy - 1.0), 0.15, color=_hex(OCEAN["bronze"]), alpha=0.6)
    ax.add_patch(dot_l)

    # Right stat — events
    ax.text(8.5, cy + 0.5, str(total_events),
            ha="center", va="center",
            fontsize=36, fontweight="bold", color=_hex(OCEAN["secondary"]))
    ax.text(8.5, cy - 0.3, "событий",
            ha="center", va="center",
            fontsize=13, color=_hex(OCEAN["muted"]))
    dot_r = plt.Circle((8.5, cy - 1.0), 0.15, color=_hex(OCEAN["secondary"]), alpha=0.6)
    ax.add_patch(dot_r)

    path = out_dir / "chart_hero_visualization.png"
    fig.savefig(path, bbox_inches="tight", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# 15. Microcharts (4 sparklines)
# ---------------------------------------------------------------------------

def chart_microchart_match_share(data: V10Data, out_dir: Path) -> Path:
    """Sparkline: match_share trend (300×100 px)."""
    timeline = data.trend.get("timeline", [])
    vals = [float(t.get("match_share", 0)) for t in timeline]
    if not vals:
        vals = [0.0]

    fig, ax = plt.subplots(figsize=(3.0, 1.0))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.plot(vals, color=_hex(OCEAN["primary"]), linewidth=2)
    ax.fill_between(range(len(vals)), vals, alpha=0.2, color=_hex(OCEAN["primary"]))
    ax.axis("off")
    fig.tight_layout(pad=0)
    path = out_dir / "chart_microchart_match_share.png"
    fig.savefig(path, dpi=100, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def chart_microchart_status_donut(data: V10Data, out_dir: Path) -> Path:
    """Micro donut: status distribution (300×300 px)."""
    sc = _status_colors()
    dist = data.pairs_by_status()
    sizes = [dist.get(s, 0) for s in V8_STATUSES]
    colors = [sc[s] for s in V8_STATUSES]
    non_zero = [(s, c) for s, c in zip(sizes, colors) if s > 0]
    if not non_zero:
        non_zero = [(1, _hex(OCEAN["muted"]))]
    sizes_nz, colors_nz = zip(*non_zero)

    fig, ax = plt.subplots(figsize=(3.0, 3.0))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.pie(
        sizes_nz,
        colors=colors_nz,
        startangle=90,
        wedgeprops={"width": 0.5, "edgecolor": "white", "linewidth": 1},
    )
    ax.axis("equal")
    path = out_dir / "chart_microchart_status_donut.png"
    fig.savefig(path, dpi=100, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def chart_microchart_rank_bar(data: V10Data, out_dir: Path) -> Path:
    """Micro horizontal bar: rank distribution (300×100 px)."""
    by_rank: dict[str, int] = {}
    for p in data.pairs:
        rp = p.get("rank_pair", "?").strip()
        by_rank[rp] = by_rank.get(rp, 0) + 1
    labels = sorted(by_rank.keys())
    vals = [by_rank[k] for k in labels]

    fig, ax = plt.subplots(figsize=(3.0, 1.0))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.barh(labels, vals, color=_hex(OCEAN["primary"]), height=0.5)
    ax.axis("off")
    fig.tight_layout(pad=0)
    path = out_dir / "chart_microchart_rank_bar.png"
    fig.savefig(path, dpi=100, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def chart_microchart_events_pulse(data: V10Data, out_dir: Path) -> Path:
    """Micro sparkline: events count v7-v10 (300×100 px)."""
    timeline = data.trend.get("timeline", [])
    vals = [int(t.get("events", 0)) for t in timeline]
    if not vals:
        vals = [0]

    fig, ax = plt.subplots(figsize=(3.0, 1.0))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.plot(vals, color=_hex(OCEAN["secondary"]), linewidth=2, marker="o", markersize=4)
    ax.fill_between(range(len(vals)), vals, alpha=0.2, color=_hex(OCEAN["secondary"]))
    ax.axis("off")
    fig.tight_layout(pad=0)
    path = out_dir / "chart_microchart_events_pulse.png"
    fig.savefig(path, dpi=100, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def build_all_charts(
    out_dir: Path | str | None = None,
    *,
    data: V10Data | None = None,
) -> dict[str, Path]:
    """Generate all 15 PNG charts. Returns mapping name → path."""
    if out_dir is None:
        resolved_out = DEFAULT_OUT_DIR
    else:
        resolved_out = Path(out_dir)
    resolved_out.mkdir(parents=True, exist_ok=True)

    if data is None:
        data = load_data()

    charts = [
        ("chart_status_pie",                chart_status_pie),
        ("chart_trend_match_share",         chart_trend_match_share),
        ("chart_trend_review_queue",        chart_trend_review_queue),
        ("chart_rank_distribution",         chart_rank_distribution),
        ("chart_correlation_heatmap",       chart_correlation_heatmap),
        ("chart_coverage_heatmap",          chart_coverage_heatmap),
        ("chart_dependency_graph",          chart_dependency_graph),
        ("chart_themes_distribution",       chart_themes_distribution),
        ("chart_priority_split",            chart_priority_split),
        ("chart_actions_severity",          chart_actions_severity),
        ("chart_sankey_rank_flow",          chart_sankey_rank_flow),
        ("chart_treemap_themes",            chart_treemap_themes),
        ("chart_journey_timeline",          chart_journey_timeline),
        ("chart_hero_visualization",        chart_hero_visualization),
        ("chart_microchart_match_share",    chart_microchart_match_share),
        ("chart_microchart_status_donut",   chart_microchart_status_donut),
        ("chart_microchart_rank_bar",       chart_microchart_rank_bar),
        ("chart_microchart_events_pulse",   chart_microchart_events_pulse),
    ]

    results: dict[str, Path] = {}
    for name, fn in charts:
        print(f"  Generating {name}...", flush=True)
        path = fn(data, resolved_out)
        results[name] = path

    return results


if __name__ == "__main__":
    paths = build_all_charts()
    print("\nGenerated charts:")
    for name, p in paths.items():
        size_kb = p.stat().st_size // 1024
        print(f"  {name}: {p} ({size_kb} KB)")
