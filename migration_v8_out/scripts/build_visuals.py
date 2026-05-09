#!/usr/bin/env python3
"""v8.2 visual layer: PNG charts for the dashboard.

Outputs (all written to /home/dev/diff/migration_v8_out/docs/visuals/):
  * heatmap_doc_x_doc.png  — 26×26 status grid with code labels
  * status_pie.png          — pie chart of pair-status distribution
  * topic_bar.png           — horizontal bar chart of events per topic
  * rank_pair_bar.png       — distribution of pairs by rank pair (1↔1, 1↔3, …)
  * cover_summary.png       — composite cover image for PDF first-page

These PNGs are then embedded by `enhance_v8.py` into the supplementary
Excel and by a follow-up PDF rebuild that adds a cover page.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from collections import Counter

import matplotlib
matplotlib.use("Agg")  # no display server in container
import matplotlib.pyplot as plt
from matplotlib import colors as mcolors
from matplotlib.patches import Patch
import numpy as np

# Ensure CJK/Cyrillic-capable font
import matplotlib.font_manager as fm
for fp in ["/usr/share/fonts/noto/NotoSans-Regular.ttf",
           "/usr/share/fonts/liberation/LiberationSans-Regular.ttf"]:
    if Path(fp).exists():
        fm.fontManager.addfont(fp)
        break
plt.rcParams["font.family"] = "Noto Sans" if Path("/usr/share/fonts/noto/NotoSans-Regular.ttf").exists() else "DejaVu Sans"
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path("/home/dev/diff/migration_v8_out")
DATA = ROOT / "data"
DOCS = ROOT / "docs"
OUT = DOCS / "visuals"
OUT.mkdir(parents=True, exist_ok=True)

# v8 status palette (matches Excel cell fills)
STATUS_COLORS = {
    "match":           "#16A34A",  # green
    "partial_overlap": "#F59E0B",  # amber
    "contradiction":   "#DC2626",  # red
    "outdated":        "#2563EB",  # blue
    "source_gap":      "#7C3AED",  # purple
    "manual_review":   "#EA580C",  # orange
    "not_comparable":  "#9CA3AF",  # gray
    "self":            "#1F2937",  # diagonal
}

# Map cell mark → status (mirror of forensic.STATUS_TO_MARK reversed)
MARK_TO_STATUS = {
    "✓": "match", "≈": "partial_overlap", "⚠": "contradiction",
    "↻": "outdated", "∅": "source_gap", "?": "manual_review",
    "—": "not_comparable",
}


def _read_csv(path: Path):
    return list(csv.DictReader(path.open(encoding="utf-8-sig"), delimiter=";"))


# ---------------------------------------------------------------------------
# 1. Heatmap of 26×26 doc×doc matrix
# ---------------------------------------------------------------------------

def make_heatmap() -> Path:
    matrix = _read_csv(DATA / "03_doc_x_doc_matrix.csv")
    docs = [r["ИД"] for r in matrix]
    codes = [r["Код"] for r in matrix]
    n = len(docs)

    status_grid = np.empty((n, n), dtype=object)
    for i, row in enumerate(matrix):
        for j, dj in enumerate(docs):
            cell = (row.get(dj) or "").strip()
            if cell == "—" and i == j:
                status_grid[i, j] = "self"
            else:
                mark = cell[0] if cell else ""
                status_grid[i, j] = MARK_TO_STATUS.get(mark, "not_comparable")

    fig, ax = plt.subplots(figsize=(11, 9.5), dpi=140)
    # Render as colored cells via imshow with custom palette index
    status_order = list(STATUS_COLORS)
    palette_idx = {s: k for k, s in enumerate(status_order)}
    int_grid = np.vectorize(palette_idx.get)(status_grid)

    cmap = mcolors.ListedColormap([STATUS_COLORS[s] for s in status_order])
    bounds = np.arange(len(status_order) + 1) - 0.5
    norm = mcolors.BoundaryNorm(bounds, cmap.N)

    im = ax.imshow(int_grid, cmap=cmap, norm=norm, aspect="equal")

    # Tick labels = code names rotated
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(codes, rotation=70, ha="right", fontsize=7)
    ax.set_yticklabels(codes, fontsize=7)
    ax.set_title("Doc × Doc — карта статусов v8 (26×26)", fontsize=12, pad=14)

    # Cell-level event count overlay
    matrix_rows = matrix
    for i, row in enumerate(matrix_rows):
        for j, dj in enumerate(docs):
            cell = (row.get(dj) or "").strip()
            if "(" in cell:
                cnt = cell[cell.index("(") + 1:cell.index(")")]
                if cnt and cnt != "0":
                    ax.text(j, i, cnt, ha="center", va="center",
                            fontsize=5.5, color="white",
                            fontweight="bold")

    # Subtle grid lines
    ax.set_xticks(np.arange(-0.5, n, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.4)
    ax.tick_params(which="minor", length=0)

    legend = [Patch(facecolor=STATUS_COLORS[s], edgecolor="black", linewidth=0.3, label=s)
              for s in ("match", "partial_overlap", "contradiction",
                        "outdated", "source_gap", "manual_review", "not_comparable")]
    ax.legend(handles=legend, loc="upper center", bbox_to_anchor=(0.5, -0.13),
              ncol=4, fontsize=8, frameon=False)

    plt.tight_layout()
    p = OUT / "heatmap_doc_x_doc.png"
    fig.savefig(p, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


# ---------------------------------------------------------------------------
# 2. Status pie chart
# ---------------------------------------------------------------------------

def make_status_pie() -> Path:
    qa = json.loads((ROOT / "logs" / "qa.json").read_text(encoding="utf-8"))
    dist = qa["status_distribution_pairs"]
    fig, ax = plt.subplots(figsize=(7, 6), dpi=140)
    labels = list(dist.keys())
    sizes = list(dist.values())
    cmap = [STATUS_COLORS.get(s, "#9CA3AF") for s in labels]
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, autopct=lambda p: f"{int(round(p * sum(sizes) / 100))}\n({p:.1f}%)",
        colors=cmap, startangle=90, wedgeprops=dict(edgecolor="white", linewidth=2),
        textprops=dict(fontsize=9),
    )
    for t in autotexts:
        t.set_color("white")
        t.set_fontweight("bold")
        t.set_fontsize(8)
    ax.set_title("Распределение пар по статусам v8 (всего 325)", fontsize=12, pad=12)
    p = OUT / "status_pie.png"
    fig.savefig(p, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


# ---------------------------------------------------------------------------
# 3. Topic bar chart
# ---------------------------------------------------------------------------

def make_topic_bar() -> Path:
    rows = _read_csv(DATA / "04_topic_x_doc.csv")
    topics, totals = [], []
    for r in rows:
        try:
            tot = int(r.get("Σ событий") or 0)
        except ValueError:
            tot = 0
        topics.append(r["Тема"])
        totals.append(tot)
    # sort by count
    pairs = sorted(zip(topics, totals), key=lambda x: x[1], reverse=True)
    topics_s, totals_s = zip(*pairs)
    fig, ax = plt.subplots(figsize=(10, max(4, 0.35 * len(topics_s))), dpi=140)
    y_pos = np.arange(len(topics_s))
    ax.barh(y_pos, totals_s, color="#2563EB", height=0.7)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(topics_s, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Σ событий (учитывается дважды: L + R)", fontsize=9)
    ax.set_title("Тематическое покрытие корпуса (v8 кластеры)", fontsize=12, pad=10)
    for i, v in enumerate(totals_s):
        ax.text(v + 4, i, str(v), va="center", fontsize=7, color="#1F2937")
    plt.tight_layout()
    p = OUT / "topic_bar.png"
    fig.savefig(p, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


# ---------------------------------------------------------------------------
# 4. Rank-pair distribution
# ---------------------------------------------------------------------------

def make_rank_pair_bar() -> Path:
    qa = json.loads((ROOT / "logs" / "qa.json").read_text(encoding="utf-8"))
    dist = qa["rank_pair_distribution"]
    keys = sorted(dist.keys())
    keys_display = [k.replace("↔", "—") for k in keys]
    vals = [dist[k] for k in keys]
    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=140)
    bars = ax.bar(keys_display, vals, color="#7C3AED", edgecolor="white", linewidth=1)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 2, str(v), ha="center",
                va="bottom", fontsize=8, fontweight="bold")
    ax.set_ylabel("Пар", fontsize=9)
    ax.set_xlabel("Ранг пары (L—R)", fontsize=9)
    ax.set_title("Распределение пар по рангам источников", fontsize=12, pad=10)
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    plt.tight_layout()
    p = OUT / "rank_pair_bar.png"
    fig.savefig(p, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


# ---------------------------------------------------------------------------
# 5. Composite cover summary
# ---------------------------------------------------------------------------

def make_cover_summary() -> Path:
    qa = json.loads((ROOT / "logs" / "qa.json").read_text(encoding="utf-8"))
    fig, axes = plt.subplots(2, 2, figsize=(11, 8.5), dpi=140)

    # Top-left: status pie
    ax = axes[0][0]
    dist = qa["status_distribution_pairs"]
    labels = list(dist.keys())
    sizes = list(dist.values())
    cmap = [STATUS_COLORS.get(s, "#9CA3AF") for s in labels]
    ax.pie(sizes, labels=labels, autopct="%1.0f%%", colors=cmap, startangle=90,
           wedgeprops=dict(edgecolor="white", linewidth=1.5),
           textprops=dict(fontsize=8))
    ax.set_title("Статусы пар (325)", fontsize=11)

    # Top-right: rank-pair bar
    ax = axes[0][1]
    rd = qa["rank_pair_distribution"]
    keys = sorted(rd.keys())
    keys_display = [k.replace("↔", "—") for k in keys]
    vals = [rd[k] for k in keys]
    ax.bar(keys_display, vals, color="#7C3AED")
    for i, v in enumerate(vals):
        ax.text(i, v + 2, str(v), ha="center", fontsize=8)
    ax.set_title("Пары × ранги источников", fontsize=11)
    ax.set_ylabel("Пар", fontsize=9)
    ax.tick_params(axis="x", labelsize=9)

    # Bottom-left: control numbers + key risks
    ax = axes[1][0]
    ax.axis("off")
    cn = qa["control_numbers_actual"]
    txt = (
        f"Источников: {cn['documents']}\n"
        f"Пар (C(n,2)): {cn['pairs']}\n"
        f"Событий: {cn['events']}\n"
        f"Очередь ручной проверки: {cn['manual_reviews']}\n"
        f"Финальные противоречия: {cn['final_contradictions']}\n"
        f"Source gaps: {cn['uncovered_theses']}\n"
        f"Defect log: {cn['defect_log']}"
    )
    ax.text(0.05, 0.95, "Контрольные числа", fontsize=12, fontweight="bold",
            transform=ax.transAxes, va="top")
    ax.text(0.05, 0.78, txt, fontsize=10, transform=ax.transAxes, va="top",
            fontfamily="monospace")

    # Bottom-right: top FA actions
    ax = axes[1][1]
    ax.axis("off")
    actions_csv = _read_csv(DATA / "10_actions_catalogue.csv")
    txt = "\n".join(
        f"{a['ID']}  {a['Категория'][:38]}{'…' if len(a['Категория']) > 38 else ''}"
        for a in actions_csv[:8]
    )
    ax.text(0.05, 0.95, "Топ FA-действий", fontsize=12, fontweight="bold",
            transform=ax.transAxes, va="top")
    ax.text(0.05, 0.78, txt, fontsize=8.5, transform=ax.transAxes, va="top",
            fontfamily="monospace")

    fig.suptitle("Forensic v8.2 — DocDiffOps", fontsize=14, fontweight="bold")
    fig.text(0.5, 0.005, f"Сгенерировано: {qa['generated_at']}",
             ha="center", fontsize=8, color="#4B5563")
    plt.tight_layout(rect=(0, 0.02, 1, 0.97))
    p = OUT / "cover_summary.png"
    fig.savefig(p, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    files = [
        make_heatmap(),
        make_status_pie(),
        make_topic_bar(),
        make_rank_pair_bar(),
        make_cover_summary(),
    ]
    for f in files:
        print(f"  ✓ {f.relative_to(ROOT)}: {f.stat().st_size:,}b")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
