"""Tests for docdiffops.forensic_correlations (Sprint 6 PR-6.1).

Covers the five public functions:
  compute_correlation_matrix, compute_claim_provenance,
  compute_dependency_graph, compute_coverage_heatmap, emit_correlation_csvs.

Run: pytest tests/unit/test_forensic_correlations.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from docdiffops.forensic_correlations import (
    compute_claim_provenance,
    compute_correlation_matrix,
    compute_coverage_heatmap,
    compute_dependency_graph,
    emit_correlation_csvs,
)

# ---------------------------------------------------------------------------
# Shared synthetic fixtures
# ---------------------------------------------------------------------------

DOCS_4: list[dict] = [
    {"id": "D01", "short": "Doc-1", "rank": 1},
    {"id": "D02", "short": "Doc-2", "rank": 1},
    {"id": "D03", "short": "Doc-3", "rank": 3},
    {"id": "D04", "short": "Doc-4", "rank": 4},
]

THEMES_3: list[dict] = [
    {"id": "T01", "name": "Theme Alpha"},
    {"id": "T02", "name": "Theme Beta"},
    {"id": "T03", "name": "Theme Gamma"},
]

# T01 covers D01 (×2) and D03 (×1); T02 covers D02 (×1); T03 has no links.
LINKS: list[dict] = [
    {"theme_id": "T01", "doc_id": "D01", "status": "match"},
    {"theme_id": "T01", "doc_id": "D01", "status": "partial_overlap"},
    {"theme_id": "T01", "doc_id": "D03", "status": "match"},
    {"theme_id": "T01", "doc_id": "D02", "status": "not_comparable"},  # excluded
    {"theme_id": "T02", "doc_id": "D02", "status": "match"},
]


# ---------------------------------------------------------------------------
# 1. test_correlation_matrix_shape
# ---------------------------------------------------------------------------


def test_correlation_matrix_shape() -> None:
    """3 themes × 4 docs: verify cell counts match the link list."""
    matrix = compute_correlation_matrix(THEMES_3, DOCS_4, LINKS)

    # All three themes present as outer keys.
    assert set(matrix.keys()) == {"T01", "T02", "T03"}

    # T01: D01→2, D03→1, D02→0 (not_comparable excluded), D04→0
    assert matrix["T01"]["D01"] == 2
    assert matrix["T01"]["D03"] == 1
    assert matrix["T01"]["D02"] == 0
    assert matrix["T01"]["D04"] == 0

    # T02: D02→1, rest→0
    assert matrix["T02"]["D02"] == 1
    assert matrix["T02"]["D01"] == 0

    # T03: all zeros (no links)
    assert all(v == 0 for v in matrix["T03"].values())

    # Inner keys are exactly the doc IDs.
    assert set(matrix["T01"].keys()) == {"D01", "D02", "D03", "D04"}


# ---------------------------------------------------------------------------
# 2. test_claim_provenance_full_chain
# ---------------------------------------------------------------------------


def test_claim_provenance_full_chain() -> None:
    """1 thesis with 2 confirming + 1 refuting events; check all output fields."""
    theses = [
        {
            "thesis_id": "TH-001",
            "thesis": "Ставка налога не должна превышать 20%",
            "theme": "T01",
            "coordinate": "D01 стр. 1; D02 критерии",
        }
    ]
    events = [
        {
            "event_id": "E01",
            "theme": "T01",
            "left_id": "D01",
            "right_id": "D02",
            "status": "match",
            "source_rank_left": "1",
            "source_rank_right": "1",
        },
        {
            "event_id": "E02",
            "theme": "T01",
            "left_id": "D01",
            "right_id": "D03",
            "status": "partial_overlap",
            "source_rank_left": "1",
            "source_rank_right": "3",
        },
        {
            "event_id": "E03",
            "theme": "T01",
            "left_id": "D02",
            "right_id": "D03",
            "status": "contradiction",
            "source_rank_left": "1",
            "source_rank_right": "3",
        },
    ]

    result = compute_claim_provenance(theses, events, DOCS_4)

    assert len(result) == 1
    row = result[0]

    assert row["thesis_id"] == "TH-001"
    assert row["primary_doc_id"] == "D01"
    assert row["primary_rank"] == "1"

    # D01 and D02 appear in confirming events (E01: match, E02: partial_overlap).
    # D03 appears in a confirming role too (right side of E02).
    confirming = set(row["confirming_docs"].split("; "))
    assert "D01" in confirming
    assert "D02" in confirming

    # D02 and D03 appear in refuting event (E03: contradiction).
    refuting = set(row["refuting_docs"].split("; "))
    assert "D02" in refuting or "D03" in refuting

    # Evidence event IDs recorded.
    evidence_ids = set(row["evidence_event_ids"].split("; "))
    assert {"E01", "E02", "E03"}.issubset(evidence_ids)


# ---------------------------------------------------------------------------
# 3. test_dependency_graph_label_mapping
# ---------------------------------------------------------------------------


def test_dependency_graph_label_mapping() -> None:
    """Russian comparison_type labels map to canonical English relation_type."""
    pair_relations = [
        {
            "left_id": "D01",
            "right_id": "D02",
            "comparison_type": "актуализация ПП2573 поправкой ПП1375",
            "status": "match",
        },
        {
            "left_id": "D02",
            "right_id": "D03",
            "comparison_type": "тематическое сопоставление",
            "status": "match",
        },
        {
            "left_id": "D03",
            "right_id": "D04",
            "comparison_type": "тематическое/архивное сопоставление",
            "status": "match",
        },
        {
            "left_id": "D01",
            "right_id": "D03",
            "comparison_type": "provenance/архивное сопоставление",
            "status": "match",
        },
        {
            "left_id": "D02",
            "right_id": "D04",
            "comparison_type": "методический/forensic контекст",
            "status": "match",
        },
    ]

    edges = compute_dependency_graph(pair_relations, DOCS_4)
    assert len(edges) == 5

    by_from_to = {(e["from_doc_id"], e["to_doc_id"]): e for e in edges}

    assert by_from_to[("D01", "D02")]["relation_type"] == "amends"
    assert by_from_to[("D02", "D03")]["relation_type"] == "references"
    assert by_from_to[("D03", "D04")]["relation_type"] == "references"
    assert by_from_to[("D01", "D03")]["relation_type"] == "provenance"
    assert by_from_to[("D02", "D04")]["relation_type"] == "methodology"


def test_dependency_graph_not_comparable_low_relevance_skipped() -> None:
    """not_comparable + низкая relevance pairs are excluded."""
    pair_relations = [
        {
            "left_id": "D01",
            "right_id": "D02",
            "comparison_type": "тематическое сопоставление",
            "status": "not_comparable",
            "relevance": "низкая",
        },
        {
            "left_id": "D02",
            "right_id": "D03",
            "comparison_type": "тематическое сопоставление",
            "status": "not_comparable",
            "relevance": "средняя",  # kept
        },
    ]
    edges = compute_dependency_graph(pair_relations, DOCS_4)
    assert len(edges) == 1
    assert edges[0]["from_doc_id"] == "D02"


# ---------------------------------------------------------------------------
# 4. test_coverage_heatmap_rank_distribution
# ---------------------------------------------------------------------------


def test_coverage_heatmap_rank_distribution() -> None:
    """Per-theme rank-bucketed counts reflect correlation matrix coverage."""
    # Build a known matrix: T01 covers D01(rank1) and D03(rank3); T02 covers D02(rank1).
    matrix = {
        "T01": {"D01": 2, "D02": 0, "D03": 1, "D04": 0},
        "T02": {"D01": 0, "D02": 1, "D03": 0, "D04": 0},
        "T03": {"D01": 0, "D02": 0, "D03": 0, "D04": 0},
    }

    heatmap = compute_coverage_heatmap(matrix, DOCS_4)

    assert set(heatmap.keys()) == {"T01", "T02", "T03"}

    # T01: 1 rank-1 doc (D01), 0 rank-2, 1 rank-3 (D03), 0 rank-4
    assert heatmap["T01"][1] == 1
    assert heatmap["T01"][2] == 0
    assert heatmap["T01"][3] == 1
    assert heatmap["T01"][4] == 0

    # T02: 1 rank-1 doc (D02)
    assert heatmap["T02"][1] == 1
    assert heatmap["T02"][3] == 0

    # T03: all zeros
    assert all(v == 0 for v in heatmap["T03"].values())

    # Row sums must equal number of docs with any coverage in the matrix.
    for tid in ("T01", "T02", "T03"):
        matrix_covered = sum(1 for cnt in matrix[tid].values() if cnt > 0)
        heatmap_sum = sum(heatmap[tid].values())
        assert heatmap_sum == matrix_covered


# ---------------------------------------------------------------------------
# 5. test_emit_csvs_have_bom
# ---------------------------------------------------------------------------


def test_emit_csvs_have_bom(tmp_path: Path) -> None:
    """Every emitted CSV file starts with the UTF-8 BOM (0xEF 0xBB 0xBF)."""
    data: dict = {
        "themes": THEMES_3,
        "docs": DOCS_4,
        "theme_doc_links": LINKS,
        "theses": [],
        "events": [],
        "pair_relations": [],
    }

    emitted = emit_correlation_csvs(data, tmp_path, write_bom=True)

    assert len(emitted) == 4
    for name, path in emitted.items():
        assert path.exists(), f"{name} was not written"
        first_bytes = path.read_bytes()[:3]
        assert first_bytes == b"\xef\xbb\xbf", (
            f"{name}: expected UTF-8 BOM, got {first_bytes!r}"
        )


def test_emit_csvs_no_bom(tmp_path: Path) -> None:
    """write_bom=False produces files without the BOM."""
    data: dict = {
        "themes": THEMES_3,
        "docs": DOCS_4,
        "theme_doc_links": LINKS,
        "theses": [],
        "events": [],
        "pair_relations": [],
    }

    emitted = emit_correlation_csvs(data, tmp_path, write_bom=False)
    for name, path in emitted.items():
        first_bytes = path.read_bytes()[:3]
        assert first_bytes != b"\xef\xbb\xbf", (
            f"{name}: unexpected BOM when write_bom=False"
        )


# ---------------------------------------------------------------------------
# 6. test_empty_inputs_dont_crash
# ---------------------------------------------------------------------------


def test_empty_inputs_dont_crash() -> None:
    """All four compute_* functions handle empty inputs without raising."""
    assert compute_correlation_matrix([], [], []) == {}
    assert compute_claim_provenance([], [], []) == []
    assert compute_dependency_graph([], []) == []
    assert compute_coverage_heatmap({}, []) == {}

    # Also: themes present but no docs/links — still no crash.
    matrix = compute_correlation_matrix(THEMES_3, [], [])
    for tid in ("T01", "T02", "T03"):
        assert matrix[tid] == {}

    # Heatmap on matrix with themes but no docs.
    heatmap = compute_coverage_heatmap(
        {"T01": {}, "T02": {}}, []
    )
    assert heatmap["T01"] == {1: 0, 2: 0, 3: 0, 4: 0}


# ---------------------------------------------------------------------------
# 7. (Optional) test_real_v10_data
# ---------------------------------------------------------------------------

_V10_INTERMEDIATE = Path(
    "/home/dev/diff/migration_v10_out/machine_appendix/v10_intermediate.json"
)


@pytest.mark.skipif(
    not _V10_INTERMEDIATE.exists(),
    reason="v10_intermediate.json not present in this environment",
)
def test_real_v10_data() -> None:
    """Load real v10 data and verify matrix dimensions match expected counts."""
    with open(_V10_INTERMEDIATE, encoding="utf-8") as fh:
        intermediate: dict = json.load(fh)

    themes: list[dict] = intermediate.get("themes", [])
    docs: list[dict] = intermediate.get("docs", [])

    # Ground-truth counts from the plan: 14 themes, 27 docs.
    assert len(themes) == 14, f"Expected 14 themes, got {len(themes)}"
    assert len(docs) == 27, f"Expected 27 docs, got {len(docs)}"

    # Build matrix with an empty link list — shape should still be correct.
    matrix = compute_correlation_matrix(themes, docs, [])
    assert len(matrix) == 14
    for row in matrix.values():
        assert len(row) == 27
