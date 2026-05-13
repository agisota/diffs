"""Build a self-contained HTML one-pager for DocDiffOps v10 presentation.

Usage (from docdiffops_mvp/):
    python -m scripts.presentation_v10.html_builder

Output: migration_v10_out/presentation/DocDiffOps_v10_presentation.html
Contract: inline CSS, inline base64 PNG, anchor navigation, < 5 MB.
"""
from __future__ import annotations

import base64
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import jinja2

from .data_loader import V10Data, load_data
from .theme import STATUS_RU, V8_STATUSES

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parents[2]
_ASSETS_DIR = _REPO_ROOT / "migration_v10_out" / "presentation" / "assets"
_OUT_PATH = _REPO_ROOT / "migration_v10_out" / "presentation" / "DocDiffOps_v10_presentation.html"

# ---------------------------------------------------------------------------
# Jinja2 env (FileSystemLoader for .j2 template)
# ---------------------------------------------------------------------------
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_SCRIPT_DIR)),
    autoescape=jinja2.select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

# ---------------------------------------------------------------------------
# Category → Russian label
# ---------------------------------------------------------------------------
_CAT_RU: dict[str, str] = {
    "brochure_vs_npa":          "брошюра против НПА",
    "department_page_split":    "раздробление ведомственной страницы",
    "secondary_digest_links":   "сноски на первичные НПА",
    "concept_supersession":     "замещение концепций",
    "amendment_chain":          "цепочка поправок",
    "amendment_to_law":         "поправки к закону",
    "amendment_to_koap":        "поправки к КоАП",
    "analytic_separation":      "разделение аналитики и НПА",
    "provenance_risk":          "риск provenance",
    "source_gap":               "пробел источника",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _b64_image(name: str) -> str:
    """Return data-URI for an asset PNG, or a 1×1 transparent PNG placeholder."""
    p = _ASSETS_DIR / name
    if not p.exists():
        # 1×1 transparent PNG fallback (44 bytes)
        _TRANSPARENT = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        return "data:image/png;base64," + base64.b64encode(_TRANSPARENT).decode()
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def _chunk(items: list[Any], size: int) -> list[tuple[str, list[Any]]]:
    """Split *items* into labelled groups of *size*."""
    result = []
    for i in range(0, len(items), size):
        chunk = items[i : i + size]
        start = i + 1
        end = i + len(chunk)
        result.append((f"Строки {start}–{end} из {len(items)}", chunk))
    return result


def _pairs_chunks(data: V10Data) -> list[tuple[str, list[dict[str, Any]]]]:
    """Build enriched pair rows with short doc names, then chunk by 50."""
    rows = []
    for p in data.pairs:
        left_id = p.get("left", "")
        right_id = p.get("right", "")
        left_doc = data.doc_by_id(left_id) or {}
        right_doc = data.doc_by_id(right_id) or {}
        rows.append({
            "id": p.get("id", ""),
            "left": left_id,
            "right": right_id,
            "left_short": (left_doc.get("code") or left_doc.get("title") or left_id)[:22],
            "right_short": (right_doc.get("code") or right_doc.get("title") or right_id)[:22],
            "topics": p.get("topics", ""),
            "v8_status": p.get("v8_status", ""),
            "events_count": p.get("events_count", "0"),
            "rank_pair": p.get("rank_pair", ""),
        })
    return _chunk(rows, 50)


def _pairs_status_table(data: V10Data) -> list[tuple[str, int, str, str]]:
    """Return [(status, count, pct_str, ru_label), ...] for all v8 statuses."""
    dist = data.pairs_by_status()
    total = max(sum(dist.values()), 1)
    result = []
    for s in V8_STATUSES:
        count = dist.get(s, 0)
        pct = f"{count / total * 100:.1f}%"
        label = STATUS_RU.get(s, s)
        result.append((s, count, pct, label))
    return result


def _rank_counts(data: V10Data) -> dict[int, int]:
    dbr = data.docs_by_rank()
    return {k: len(v) for k, v in dbr.items()}


def _theme_catalog(data: V10Data) -> list[tuple[str, str, int]]:
    """Return [(theme_id, theme_name, doc_count), ...]."""
    counts: dict[str, int] = {}
    names: dict[str, str] = {}
    for row in data.theme_doc:
        tid = row.get("theme_id", "")
        tname = row.get("theme", "")
        if tid:
            counts[tid] = counts.get(tid, 0) + 1
            names[tid] = tname
    return [(tid, names[tid], counts[tid]) for tid in sorted(counts)]


def _themes_list(data: V10Data) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    for row in data.theme_doc:
        tid = row.get("theme_id", "")
        tname = row.get("theme", "")
        if tid and tid not in seen:
            seen[tid] = tname
    return [(k, v) for k, v in sorted(seen.items())]


def _provenance_counts(data: V10Data) -> list[tuple[str, int]]:
    ctr = Counter(p.get("status", "") for p in data.provenance)
    # Keep only simple short statuses (not full URLs) for display
    simple: dict[str, int] = {}
    url_count = 0
    for status, count in ctr.items():
        if status.startswith("http"):
            url_count += count
        else:
            simple[status] = simple.get(status, 0) + count
    result = sorted(simple.items(), key=lambda x: -x[1])
    if url_count:
        result.append(("(URL-статусы)", url_count))
    return result


def _top_doc_types(data: V10Data) -> list[tuple[str, int]]:
    ctr = Counter(d.get("type", "") for d in data.documents)
    return ctr.most_common(5)


def _review_owners_top(data: V10Data) -> list[tuple[str, int]]:
    ctr = Counter(r.get("owner", "") for r in data.review_queue)
    return ctr.most_common(5)


def _dep_rel_counts(data: V10Data) -> list[tuple[str, int]]:
    ctr = Counter(r.get("relation_type", "") for r in data.dependency_graph)
    return sorted(ctr.items(), key=lambda x: -x[1])


def _actions_table(data: V10Data) -> list[dict[str, Any]]:
    result = []
    for a in data.actions:
        result.append({
            "id": a.get("id", ""),
            "cat_ru": _CAT_RU.get(a.get("category", ""), a.get("category", "")),
            "severity": a.get("severity", ""),
            "where": a.get("where", ""),
            "what_is_wrong": a.get("what_is_wrong", ""),
            "what_to_do": a.get("what_to_do", ""),
            "owner": a.get("owner", ""),
        })
    return result


def _trend_timeline(data: V10Data) -> list[dict[str, Any]]:
    return data.trend.get("timeline", [])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _critical_pairs(data: V10Data) -> list[dict[str, Any]]:
    """Return enriched critical pair dicts (contradiction + partial_overlap)."""
    rows = []
    for p in data.pairs:
        status = p.get("v8_status", "")
        if status not in ("contradiction", "partial_overlap"):
            continue
        left_id = p.get("left", "")
        right_id = p.get("right", "")
        left_doc = data.doc_by_id(left_id) or {}
        right_doc = data.doc_by_id(right_id) or {}
        rows.append({
            "id": p.get("id", ""),
            "left": left_id,
            "right": right_id,
            "left_short": (left_doc.get("code") or left_doc.get("title") or left_id)[:22],
            "right_short": (right_doc.get("code") or right_doc.get("title") or right_id)[:22],
            "topics": p.get("topics", ""),
            "v8_status": status,
            "events_count": p.get("events_count", "0"),
            "rank_pair": p.get("rank_pair", ""),
        })
    return rows


def _select_top_events(data: V10Data) -> list[dict[str, Any]]:
    """1 contradiction + 6 partial_overlap + 3 outdated, sorted by confidence desc."""
    from .theme import V8_STATUSES as _V8S
    by_status: dict[str, list[dict[str, Any]]] = {s: [] for s in _V8S}
    for ev in data.events_all:
        s = ev.get("status", "")
        if s in by_status:
            by_status[s].append(ev)
    for s in by_status:
        by_status[s].sort(
            key=lambda e: float(e.get("confidence", "0") or "0"),
            reverse=True,
        )
    selected: list[dict[str, Any]] = []
    selected.extend(by_status.get("contradiction", [])[:1])
    selected.extend(by_status.get("partial_overlap", [])[:6])
    selected.extend(by_status.get("outdated", [])[:3])
    return selected[:10]


def _event_detail_cards(data: V10Data) -> list[dict[str, Any]]:
    """Build enriched card dicts for the 10 selected events."""
    cards = []
    for ev in _select_top_events(data):
        cards.append({
            "event_id": ev.get("event_id", ""),
            "theme": ev.get("theme", ""),
            "status": ev.get("status", ""),
            "claim_left": ev.get("claim_left", ""),
            "left_id": ev.get("left_id", ""),
            "left_doc": ev.get("left_doc", ""),
            "evidence_right": ev.get("evidence_right", ""),
            "right_id": ev.get("right_id", ""),
            "right_doc": ev.get("right_doc", ""),
            "conclusion": ev.get("conclusion", ""),
            "legal_coordinate": ev.get("legal_coordinate", ""),
            "confidence": ev.get("confidence", ""),
        })
    return cards


def _theme_cards(data: V10Data, n: int = 14) -> list[dict[str, Any]]:
    """Build enriched theme card dicts for top n themes."""
    # Build theme meta
    theme_meta: dict[str, dict[str, Any]] = {}
    for row in data.theme_doc:
        tid = row.get("theme_id", "")
        if not tid:
            continue
        if tid not in theme_meta:
            theme_meta[tid] = {
                "id": tid,
                "name": row.get("theme", ""),
                "doc_count": 0,
                "event_count": 0,
            }
        theme_meta[tid]["doc_count"] += 1
    for ev in data.events_all:
        tid = ev.get("theme_id", "")
        if tid in theme_meta:
            theme_meta[tid]["event_count"] += 1
    themes = sorted(theme_meta.values(), key=lambda t: -t["event_count"])[:n]

    cards = []
    for theme in themes:
        tid = theme["id"]
        docs_in_theme = []
        for row in data.theme_doc:
            if row.get("theme_id") != tid:
                continue
            doc_id = row.get("doc_id", "")
            d = data.doc_by_id(doc_id)
            if d:
                docs_in_theme.append({
                    "id": doc_id,
                    "code": (d.get("code") or "")[:18],
                    "rank": d.get("rank", ""),
                    "role": (row.get("role") or "")[:16],
                })
        docs_in_theme = docs_in_theme[:8]

        # Status breakdown
        status_breakdown: dict[str, int] = {}
        for ev in data.events_all:
            if ev.get("theme_id") == tid:
                s = ev.get("status", "")
                status_breakdown[s] = status_breakdown.get(s, 0) + 1

        theses_for_theme = [
            t for t in data.theses if t.get("theme", "") == theme["name"]
        ][:3]
        thesis_texts = [
            (t.get("thesis") or t.get("claim_text") or "")[:120]
            for t in theses_for_theme
        ]

        review_count = sum(
            1 for r in data.review_queue if r.get("theme", "") == theme["name"]
        )

        cards.append({
            "id": tid,
            "name": theme["name"],
            "doc_count": theme["doc_count"],
            "event_count": theme["event_count"],
            "review_count": review_count,
            "docs_table": docs_in_theme,
            "status_breakdown": status_breakdown,
            "theses": thesis_texts,
        })
    return cards


def _spotlight_docs(data: V10Data) -> list[dict[str, Any]]:
    """Build enriched spotlight dicts for D18, D24, D27."""
    target_ids = ("D18", "D24", "D27")
    ordered: dict[str, dict[str, Any] | None] = {doc_id: None for doc_id in target_ids}
    for d in data.documents:
        if d.get("id") in target_ids:
            ordered[d["id"]] = dict(d)
    result = []
    for doc_id, d in ordered.items():
        if d is None:
            continue
        doc_code = d.get("code", "")
        theses_for_doc = [
            t for t in data.theses if t.get("source_doc", "") == doc_code
        ][:3]
        top_theses = [
            (t.get("thesis") or t.get("claim_text") or "")[:120]
            for t in theses_for_doc
        ]
        refs_out = [e for e in data.dependency_graph if e.get("from_doc_id") == doc_id][:5]
        refs_in = [e for e in data.dependency_graph if e.get("to_doc_id") == doc_id][:5]
        result.append({
            "id": doc_id,
            "code": doc_code,
            "title": d.get("title", "")[:60],
            "type": d.get("type", ""),
            "rank": d.get("rank", ""),
            "url": d.get("url", "")[:80],
            "top_theses": top_theses,
            "refs_out": [{"id": e.get("to_doc_id", ""), "rel": e.get("relation_type", "")} for e in refs_out],
            "refs_in": [{"id": e.get("from_doc_id", ""), "rel": e.get("relation_type", "")} for e in refs_in],
        })
    return result


def build_html(out_path: Path | None = None, *, data: V10Data | None = None) -> Path:
    """Render the HTML one-pager and write to *out_path*.

    Returns the resolved output path.
    """
    if data is None:
        data = load_data()
    if out_path is None:
        out_path = _OUT_PATH

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cn = data.control_numbers
    dbr = data.docs_by_rank()
    rank1_docs = dbr.get(1, [])
    rank23_docs = dbr.get(2, []) + dbr.get(3, [])

    # Build events_chunks with plain dict access
    events_rows = []
    for ev in data.events_all:
        events_rows.append({
            "event_id": ev.get("event_id", ""),
            "theme": ev.get("theme", ""),
            "left_id": ev.get("left_id", ""),
            "left_doc": ev.get("left_doc", ""),
            "right_id": ev.get("right_id", ""),
            "right_doc": ev.get("right_doc", ""),
            "claim_left": ev.get("claim_left", ""),
            "evidence_right": ev.get("evidence_right", ""),
            "status": ev.get("status", ""),
        })

    review_high_prio = [r for r in data.review_queue if r.get("priority") in ("P0", "P1")]
    review_p2 = [r for r in data.review_queue if r.get("priority") == "P2"]

    prio = data.review_by_priority()

    template = _jinja_env.get_template("html_template.j2")
    rendered = template.render(
        # Cover / global
        subtitle=(
            "Криминалистическое сравнение корпуса нормативных и аналитических "
            "документов миграционной политики РФ"
        ),
        qa_passed=data.qa.get("passed", 12),
        qa_total=data.qa.get("total", 12),
        # Executive
        cn_documents=cn.get("documents", 27),
        cn_pairs=cn.get("pairs", 351),
        cn_events=cn.get("events", 312),
        pairs_status_table=_pairs_status_table(data),
        # Corpus
        rank_counts=_rank_counts(data),
        rank1_docs=[
            {
                "id": d.get("id", ""),
                "code": d.get("code", ""),
                "rank": d.get("rank", ""),
                "type": d.get("type", ""),
                "title": d.get("title", ""),
            }
            for d in rank1_docs
        ],
        rank23_docs=[
            {
                "id": d.get("id", ""),
                "code": d.get("code", ""),
                "rank": d.get("rank", ""),
                "type": d.get("type", ""),
                "title": d.get("title", ""),
            }
            for d in rank23_docs
        ],
        top_doc_types=_top_doc_types(data),
        themes_list=_themes_list(data),
        provenance_counts=_provenance_counts(data),
        # Pair matrix
        pairs_chunks=_pairs_chunks(data),
        # Events
        events_chunks=_chunk(events_rows, 50),
        # Themes
        theme_catalog=_theme_catalog(data),
        dep_graph_count=len(data.dependency_graph),
        dep_rel_counts=_dep_rel_counts(data),
        # Review queue
        review_high_prio=review_high_prio,
        review_p2=review_p2,
        prio_p0=prio.get("P0", 4),
        prio_p1=prio.get("P1", 2),
        prio_p2=prio.get("P2", 97),
        review_owners_top=_review_owners_top(data),
        # Trend & QA
        trend_timeline=_trend_timeline(data),
        qa_checks=data.qa.get("checks", []),
        # Actions
        actions_table=_actions_table(data),
        actions_detail=_actions_table(data),
        # Wave F: new sections
        critical_pairs=_critical_pairs(data),
        event_detail_cards=_event_detail_cards(data),
        theme_cards=_theme_cards(data, n=14),
        spotlight_docs=_spotlight_docs(data),
        # Charts (base64 PNG)
        chart_status_pie=_b64_image("chart_status_pie.png"),
        chart_trend_match_share=_b64_image("chart_trend_match_share.png"),
        chart_trend_review_queue=_b64_image("chart_trend_review_queue.png"),
        chart_rank_distribution=_b64_image("chart_rank_distribution.png"),
        chart_themes_distribution=_b64_image("chart_themes_distribution.png"),
        chart_correlation_heatmap=_b64_image("chart_correlation_heatmap.png"),
        chart_coverage_heatmap=_b64_image("chart_coverage_heatmap.png"),
        chart_dependency_graph=_b64_image("chart_dependency_graph.png"),
        chart_priority_split=_b64_image("chart_priority_split.png"),
        chart_actions_severity=_b64_image("chart_actions_severity.png"),
        chart_hero_visualization=_b64_image("chart_hero_visualization.png"),
    )

    out_path.write_text(rendered, encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    print("Loading v10 data...", flush=True)
    data = load_data()
    print(f"  docs={len(data.documents)}, pairs={len(data.pairs)}, events={len(data.events_all)}")
    print("Rendering HTML...", flush=True)
    out = build_html(data=data)
    size_kb = out.stat().st_size // 1024
    print(f"  Written: {out}")
    print(f"  Size: {size_kb} KB ({out.stat().st_size:,} bytes)")
    if out.stat().st_size > 5 * 1024 * 1024:
        print("WARNING: HTML exceeds 5 MB limit!", file=sys.stderr)
        sys.exit(1)
    print("Done.")


if __name__ == "__main__":
    main()
