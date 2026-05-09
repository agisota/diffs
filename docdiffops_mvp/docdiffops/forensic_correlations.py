"""Cross-pair correlation analyses for DocDiffOps v10.

This module implements the four cross-pair analyses described in §4.2 of the
v10 forensic plan (Sprint 6, PR-6.1). The logic is lifted from the reference
script ``migration_v10_out/scripts/02_correlations.py`` and repackaged as
clean, pure functions with no filesystem side effects, no external dependencies
beyond stdlib, and full mypy-strict type annotations.

All functions follow the v8 forensic bundle contract defined in
``docdiffops.forensic`` and ``docdiffops.forensic_schema``.  Empty inputs
always produce empty outputs without raising exceptions.

Sprint 6 plan: ``.omx/plans/sprint6-pr1-pr4-plan.md``
Reference implementation: ``migration_v10_out/scripts/02_correlations.py``
"""
from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Relation type mapping (Russian comparison_type → canonical)
# Discovered from v10 data exploration in 02_correlations.py; documented here
# to serve as the authoritative reference.
# ---------------------------------------------------------------------------

_RELATION_MAP: dict[str, str] = {
    "актуализация ПП2573 поправкой ПП1375": "amends",
    "тематическое сопоставление": "references",
    "тематическое/архивное сопоставление": "references",
    "интегральное тематическое сопоставление": "references",
    "provenance/архивное сопоставление": "provenance",
    "методический/forensic контекст": "methodology",
}

# Statuses treated as confirming / refuting for claim-provenance analysis.
_CONFIRM_STATUSES: frozenset[str] = frozenset({"match", "partial_overlap"})
_REFUTE_STATUSES: frozenset[str] = frozenset({"contradiction", "manual_review"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_correlation_matrix(
    themes: list[dict[str, Any]],
    docs: list[dict[str, Any]],
    theme_doc_links: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    """Build a theme × document coverage count matrix.

    Each cell ``matrix[theme_id][doc_id]`` records how many theme-doc link
    entries (from ``theme_doc_links``) connect that theme to that document.
    Links whose status is ``"not_comparable"`` are excluded.  Themes with no
    links receive all-zero rows so coverage gaps are preserved.

    Args:
        themes: List of theme dicts, each with at least an ``"id"`` key.
        docs: List of document dicts, each with at least an ``"id"`` key.
        theme_doc_links: List of dicts with keys ``"theme_id"``, ``"doc_id"``,
            and optionally ``"status"``.

    Returns:
        Nested dict ``{theme_id: {doc_id: count, ...}, ...}``.  Order of
        outer keys follows ``themes`` list order; order of inner keys follows
        ``docs`` list order.
    """
    if not themes and not docs:
        return {}

    doc_ids: list[str] = [str(d.get("id", "")) for d in docs]
    theme_ids: list[str] = [str(t.get("id", "")) for t in themes]

    # Count non-not_comparable links per (theme_id, doc_id).
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for link in theme_doc_links:
        tid = str(link.get("theme_id", "")).strip()
        did = str(link.get("doc_id", "")).strip()
        status = str(link.get("status", "")).strip()
        if tid and did and status != "not_comparable":
            counts[(tid, did)] += 1

    matrix: dict[str, dict[str, int]] = {}
    for tid in theme_ids:
        row: dict[str, int] = {}
        for did in doc_ids:
            row[did] = counts.get((tid, did), 0)
        matrix[tid] = row
    return matrix


def compute_claim_provenance(
    theses: list[dict[str, Any]],
    events: list[dict[str, Any]],
    docs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map each thesis/claim to its confirming and refuting evidence documents.

    For each thesis the function:

    1. Extracts ``D##``-style document IDs from the thesis ``"coordinate"``
       field (e.g. ``"D18 стр. 1 RU; D20 критерии"``).
    2. Finds events whose ``theme``/``theme_id`` matches the thesis theme
       **and** whose ``left_id`` / ``right_id`` appear in the extracted doc IDs
       (or all theme events when the coordinate yields no doc IDs).
    3. Partitions events by status into confirming (``match``,
       ``partial_overlap``) and refuting (``contradiction``,
       ``manual_review``) sets.

    Args:
        theses: List of thesis dicts with keys ``"thesis_id"``, ``"thesis"``,
            ``"theme"`` / ``"theme_id"``, and optionally ``"coordinate"``.
        events: List of event dicts with keys ``"theme"`` / ``"theme_id"``,
            ``"left_id"``, ``"right_id"``, ``"status"``,
            ``"source_rank_left"``, ``"source_rank_right"``, ``"event_id"``.
        docs: List of document dicts with at least ``"id"`` and ``"rank"``.

    Returns:
        One dict per thesis with keys: ``thesis_id``, ``thesis_text``,
        ``primary_doc_id``, ``primary_rank``, ``confirming_docs``,
        ``confirming_ranks``, ``refuting_docs``, ``refuting_ranks``,
        ``evidence_event_ids``.
    """
    if not theses:
        return []

    doc_by_id: dict[str, dict[str, Any]] = {
        str(d.get("id", "")): d for d in docs
    }

    result: list[dict[str, Any]] = []
    for th in theses:
        tid = str(th.get("thesis_id", "")).strip()
        thesis_text = str(th.get("thesis", "")).strip()
        theme = str(th.get("theme", th.get("theme_id", ""))).strip()
        coord = str(th.get("coordinate", ""))
        coord_docs = _extract_doc_ids_from_coord(coord)

        primary_did = coord_docs[0] if coord_docs else ""
        primary_rank: str = ""
        if primary_did and primary_did in doc_by_id:
            primary_rank = str(doc_by_id[primary_did].get("rank", ""))

        # Relevant events: same theme AND (left/right in coord_docs, or all
        # when coord_docs is empty).
        rel_events = [
            e for e in events
            if (
                str(e.get("theme_id", e.get("theme", ""))).strip() == theme
            ) and (
                not coord_docs
                or str(e.get("left_id", "")) in coord_docs
                or str(e.get("right_id", "")) in coord_docs
            )
        ]

        confirming: list[str] = []
        confirming_ranks: list[str] = []
        refuting: list[str] = []
        refuting_ranks: list[str] = []
        evidence_eids: list[str] = []

        for ev in rel_events:
            ev_status = str(ev.get("status", "")).strip()
            for side, rank_key in (
                ("left_id", "source_rank_left"),
                ("right_id", "source_rank_right"),
            ):
                did = str(ev.get(side, "")).strip()
                if not did:
                    continue
                rank = str(ev.get(rank_key, "")).strip()
                if ev_status in _CONFIRM_STATUSES:
                    if did not in confirming:
                        confirming.append(did)
                        confirming_ranks.append(rank)
                elif ev_status in _REFUTE_STATUSES:
                    if did not in refuting:
                        refuting.append(did)
                        refuting_ranks.append(rank)
            eid = str(ev.get("event_id", "")).strip()
            if eid and eid not in evidence_eids:
                evidence_eids.append(eid)

        result.append(
            {
                "thesis_id": tid,
                "thesis_text": thesis_text,
                "primary_doc_id": primary_did,
                "primary_rank": primary_rank,
                "confirming_docs": "; ".join(confirming),
                "confirming_ranks": "; ".join(confirming_ranks),
                "refuting_docs": "; ".join(refuting),
                "refuting_ranks": "; ".join(refuting_ranks),
                "evidence_event_ids": "; ".join(evidence_eids),
            }
        )
    return result


def compute_dependency_graph(
    pair_relations: list[dict[str, Any]],
    docs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build document-to-document dependency edges from pair comparison types.

    Russian ``comparison_type`` labels are mapped to canonical English
    relation types (``amends``, ``references``, ``provenance``,
    ``methodology``).  Unknown labels pass through as-is so future
    comparison types are not silently discarded.  Pairs where both status
    is ``"not_comparable"`` **and** relevance is ``"низкая"`` are skipped
    as structural noise.

    Args:
        pair_relations: List of pair dicts with keys ``"left_id"``,
            ``"right_id"``, ``"comparison_type"``, ``"status"``,
            ``"relevance"`` (optional), ``"left"`` and ``"right"``
            (short labels, used as fallback).
        docs: List of document dicts with at least ``"id"`` and optionally
            ``"short"`` for display labels.

    Returns:
        List of edge dicts, each with keys: ``from_doc_id``,
        ``from_doc_short``, ``to_doc_id``, ``to_doc_short``,
        ``relation_type``, ``weight``.
    """
    if not pair_relations:
        return []

    doc_by_id: dict[str, dict[str, Any]] = {
        str(d.get("id", "")): d for d in docs
    }

    edges: list[dict[str, Any]] = []
    for row in pair_relations:
        status = str(row.get("status", "")).strip()
        relevance = str(row.get("relevance", "")).strip()
        # Skip low-relevance not_comparable noise.
        if status == "not_comparable" and relevance == "низкая":
            continue
        from_id = str(row.get("left_id", "")).strip()
        to_id = str(row.get("right_id", "")).strip()
        if not from_id or not to_id:
            continue
        ctype = str(row.get("comparison_type", "")).strip()
        rel = _RELATION_MAP.get(ctype, ctype)

        from_doc = doc_by_id.get(from_id, {})
        to_doc = doc_by_id.get(to_id, {})
        edges.append(
            {
                "from_doc_id": from_id,
                "from_doc_short": from_doc.get(
                    "short", str(row.get("left", from_id))
                ),
                "to_doc_id": to_id,
                "to_doc_short": to_doc.get(
                    "short", str(row.get("right", to_id))
                ),
                "relation_type": rel,
                "weight": 1,
            }
        )
    return edges


def compute_coverage_heatmap(
    correlation_matrix: dict[str, dict[str, int]],
    docs: list[dict[str, Any]],
) -> dict[str, dict[int, int]]:
    """Count coverage per theme broken down by document source rank.

    For each theme the function counts how many documents with a given rank
    have at least one coverage link (i.e. ``correlation_matrix[theme][doc] > 0``).
    This reveals themes covered only by analytics (rank 3) without primary
    regulation (ranks 1–2).

    Args:
        correlation_matrix: Output of :func:`compute_correlation_matrix`,
            ``{theme_id: {doc_id: count, ...}, ...}``.
        docs: List of document dicts with at least ``"id"`` and ``"rank"``.
            ``rank`` should be an integer or a string parseable as one.

    Returns:
        ``{theme_id: {1: n, 2: n, 3: n, 4: n}}``.  Only ranks 1–4 are
        tracked; documents with other rank values are ignored.
    """
    if not correlation_matrix:
        return {}

    doc_rank: dict[str, int] = {}
    for d in docs:
        did = str(d.get("id", ""))
        raw_rank = d.get("rank", "")
        try:
            doc_rank[did] = int(raw_rank)
        except (ValueError, TypeError):
            pass

    heatmap: dict[str, dict[int, int]] = {}
    for tid, row in correlation_matrix.items():
        rank_counts: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0}
        for did, cnt in row.items():
            if cnt > 0:
                r = doc_rank.get(did)
                if r in rank_counts:
                    rank_counts[r] += 1
        heatmap[tid] = rank_counts
    return heatmap


def emit_correlation_csvs(
    bundle_or_data: dict[str, Any],
    out_dir: Path,
    *,
    write_bom: bool = True,
) -> dict[str, Path]:
    """Compute all four correlation analyses and write BOM-prefixed CSVs.

    Accepts either a forensic bundle dict or a raw data dict.  Required keys:
    ``themes``, ``docs``, ``theme_doc_links``, ``theses``, ``events``,
    ``pair_relations``.  Missing keys default to empty lists.

    The four output files are:

    * ``correlation_matrix.csv`` — theme × doc coverage counts
    * ``claim_provenance.csv`` — thesis → confirming / refuting docs
    * ``dependency_graph.csv`` — doc → doc edges
    * ``coverage_heatmap.csv`` — theme × rank-bucketed counts

    Args:
        bundle_or_data: Input data dict with the keys listed above.
        out_dir: Directory to write CSVs into; created if absent.
        write_bom: When ``True`` (default), prepend UTF-8 BOM
            (``\\xef\\xbb\\xbf``) so Excel opens the file without
            an encoding wizard.

    Returns:
        Dict mapping short filename (without directory) to absolute ``Path``.

    Raises:
        OSError: If ``out_dir`` cannot be created or files cannot be written.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    themes: list[dict[str, Any]] = list(bundle_or_data.get("themes", []))
    docs: list[dict[str, Any]] = list(bundle_or_data.get("docs", []))
    theme_doc_links: list[dict[str, Any]] = list(
        bundle_or_data.get("theme_doc_links", [])
    )
    theses: list[dict[str, Any]] = list(bundle_or_data.get("theses", []))
    events: list[dict[str, Any]] = list(bundle_or_data.get("events", []))
    pair_relations: list[dict[str, Any]] = list(
        bundle_or_data.get("pair_relations", [])
    )

    corr_matrix = compute_correlation_matrix(themes, docs, theme_doc_links)
    provenance = compute_claim_provenance(theses, events, docs)
    dep_graph = compute_dependency_graph(pair_relations, docs)
    heatmap = compute_coverage_heatmap(corr_matrix, docs)

    doc_ids: list[str] = [str(d.get("id", "")) for d in docs]
    theme_names: dict[str, str] = {
        str(t.get("id", "")): str(t.get("name", "")) for t in themes
    }

    emitted: dict[str, Path] = {}

    # --- correlation_matrix.csv ---
    cm_fieldnames = ["theme_id", "theme_name"] + doc_ids
    cm_rows: list[dict[str, Any]] = []
    for tid, row in corr_matrix.items():
        r: dict[str, Any] = {
            "theme_id": tid,
            "theme_name": theme_names.get(tid, ""),
        }
        r.update(row)
        cm_rows.append(r)
    emitted["correlation_matrix.csv"] = _write_csv(
        out_dir / "correlation_matrix.csv",
        cm_fieldnames,
        cm_rows,
        write_bom=write_bom,
    )

    # --- claim_provenance.csv ---
    prov_fieldnames = [
        "thesis_id",
        "thesis_text",
        "primary_doc_id",
        "primary_rank",
        "confirming_docs",
        "confirming_ranks",
        "refuting_docs",
        "refuting_ranks",
        "evidence_event_ids",
    ]
    emitted["claim_provenance.csv"] = _write_csv(
        out_dir / "claim_provenance.csv",
        prov_fieldnames,
        provenance,
        write_bom=write_bom,
    )

    # --- dependency_graph.csv ---
    dep_fieldnames = [
        "from_doc_id",
        "from_doc_short",
        "to_doc_id",
        "to_doc_short",
        "relation_type",
        "weight",
    ]
    emitted["dependency_graph.csv"] = _write_csv(
        out_dir / "dependency_graph.csv",
        dep_fieldnames,
        dep_graph,
        write_bom=write_bom,
    )

    # --- coverage_heatmap.csv ---
    heat_fieldnames = [
        "theme_id",
        "theme_name",
        "rank_1",
        "rank_2",
        "rank_3",
        "rank_4",
    ]
    heat_rows: list[dict[str, Any]] = []
    for tid, rank_counts in heatmap.items():
        heat_rows.append(
            {
                "theme_id": tid,
                "theme_name": theme_names.get(tid, ""),
                "rank_1": rank_counts.get(1, 0),
                "rank_2": rank_counts.get(2, 0),
                "rank_3": rank_counts.get(3, 0),
                "rank_4": rank_counts.get(4, 0),
            }
        )
    emitted["coverage_heatmap.csv"] = _write_csv(
        out_dir / "coverage_heatmap.csv",
        heat_fieldnames,
        heat_rows,
        write_bom=write_bom,
    )

    return emitted


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_doc_ids_from_coord(coord: str) -> list[str]:
    """Extract ``D##``-style doc ID tokens from a coordinate string."""
    return re.findall(r"\bD\d+\b", coord)


def _write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, Any]],
    *,
    write_bom: bool,
) -> Path:
    """Write rows to a CSV file, optionally with a UTF-8 BOM prefix.

    Args:
        path: Destination file path.
        fieldnames: Ordered column names.
        rows: List of row dicts; extra keys are silently ignored.
        write_bom: Prepend UTF-8 BOM when ``True``.

    Returns:
        The ``path`` argument (for call-site convenience).
    """
    # Build CSV content in memory first so we can prepend BOM atomically.
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\r\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    content = buf.getvalue()

    encoding = "utf-8-sig" if write_bom else "utf-8"
    with open(path, "w", encoding=encoding, newline="") as fh:
        fh.write(content)
    return path
