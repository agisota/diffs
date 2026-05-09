"""Forensic v8 contract tests (TDD).

These tests pin the v8 cross-comparison contract that DocDiffOps must
implement to produce evidence-grade output equivalent to the migration
v8 reference package (``/home/dev/diff/migration_v8_out``):

  * Status scale: match | partial_overlap | contradiction | outdated |
    source_gap | manual_review | not_comparable.
  * Hierarchy invariant: rank-3 ↔ rank-1 → manual_review (rank-3 cannot
    refute rank-1 directly, even if events look like ``contradicts``).
  * Topic clustering: stable cluster IDs (T01..) for forensic reports.
  * Amendment graph drives ``outdated`` for the older side.
  * Bundle schema: every key the renderers consume is present.

Run: pytest tests/unit/test_forensic.py -v
"""
from __future__ import annotations

import pytest

from docdiffops.forensic import (
    EVENT_STATUS_TO_V8,
    V8_STATUSES,
    aggregate_pair_status_v8,
    build_forensic_bundle,
    cluster_topic_v8,
    DEFAULT_TOPIC_CLUSTERS,
    derive_outdated,
)


# ---------------------------------------------------------------------------
# Status scale
# ---------------------------------------------------------------------------


def test_v8_statuses_exact():
    assert set(V8_STATUSES) == {
        "match",
        "partial_overlap",
        "contradiction",
        "outdated",
        "source_gap",
        "manual_review",
        "not_comparable",
    }


def test_event_status_translation_covers_docdiffops_vocabulary():
    """Every existing DocDiffOps event status must map to a v8 status."""
    for src in ("same", "partial", "contradicts", "modified",
                "added", "deleted", "manual_review", "not_found"):
        assert src in EVENT_STATUS_TO_V8
        assert EVENT_STATUS_TO_V8[src] in V8_STATUSES


# ---------------------------------------------------------------------------
# Pair-status aggregation
# ---------------------------------------------------------------------------


def _ev(status, severity="medium"):
    return {"status": status, "severity": severity}


def test_aggregate_empty_events_is_not_comparable():
    out = aggregate_pair_status_v8([], left_rank=1, right_rank=1)
    assert out == "not_comparable"


def test_aggregate_all_match():
    out = aggregate_pair_status_v8(
        [_ev("same"), _ev("same")], left_rank=1, right_rank=1
    )
    assert out == "match"


def test_aggregate_partial_dominates_match():
    out = aggregate_pair_status_v8(
        [_ev("same"), _ev("partial")], left_rank=1, right_rank=1
    )
    assert out == "partial_overlap"


def test_aggregate_manual_review_overrides_everything():
    out = aggregate_pair_status_v8(
        [_ev("same"), _ev("manual_review"), _ev("partial")],
        left_rank=1, right_rank=1,
    )
    assert out == "manual_review"


def test_aggregate_contradicts_event_is_contradiction():
    out = aggregate_pair_status_v8(
        [_ev("contradicts", "high")],
        left_rank=1, right_rank=1,
    )
    assert out == "contradiction"


def test_aggregate_modified_added_deleted_count_as_partial():
    """DocDiffOps emits modified/added/deleted; from a v8 lens these are
    partial unless they cluster into a contradiction."""
    out = aggregate_pair_status_v8(
        [_ev("modified"), _ev("added"), _ev("deleted")],
        left_rank=1, right_rank=1,
    )
    assert out == "partial_overlap"


# ---------------------------------------------------------------------------
# Rank invariant: rank-3 ↔ rank-1 → manual_review
# ---------------------------------------------------------------------------


def test_rank3_rank1_pair_with_match_events_is_manual_review():
    """A rank-3 (analytics) cannot ratify a rank-1 NPA; must be manual_review."""
    out = aggregate_pair_status_v8(
        [_ev("same")], left_rank=3, right_rank=1
    )
    assert out == "manual_review"


def test_rank3_rank1_pair_with_partial_is_manual_review():
    out = aggregate_pair_status_v8(
        [_ev("partial")], left_rank=3, right_rank=1
    )
    assert out == "manual_review"


def test_rank3_rank1_pair_no_events_stays_not_comparable():
    """Empty events stay not_comparable even for rank-3↔rank-1."""
    out = aggregate_pair_status_v8([], left_rank=3, right_rank=1)
    assert out == "not_comparable"


def test_rank3_rank1_pair_with_contradicts_becomes_manual_review():
    """Even an explicit ``contradicts`` from a rank-3 source is downgraded
    to manual_review — the analyst cannot directly contradict an NPA."""
    out = aggregate_pair_status_v8(
        [_ev("contradicts", "high")], left_rank=3, right_rank=1
    )
    assert out == "manual_review"


def test_rank1_rank2_pair_keeps_natural_status():
    """Departmental ↔ NPA pairs are evaluated normally."""
    out = aggregate_pair_status_v8(
        [_ev("partial")], left_rank=2, right_rank=1
    )
    assert out == "partial_overlap"


# ---------------------------------------------------------------------------
# Explicit contradiction overrides (final v7 contradictions C-01..C-03)
# ---------------------------------------------------------------------------


def test_known_contradiction_pair_overrides_to_contradiction():
    """Pairs in the known-contradiction list always emit ``contradiction``."""
    out = aggregate_pair_status_v8(
        [_ev("partial")],
        left_rank=2, right_rank=1,
        known_contradictions=[("D10", "D26")],
        left_id="D10", right_id="D26",
    )
    assert out == "contradiction"


def test_known_contradiction_works_in_either_direction():
    out = aggregate_pair_status_v8(
        [_ev("partial")],
        left_rank=1, right_rank=2,
        known_contradictions=[("D10", "D26")],
        left_id="D26", right_id="D10",
    )
    assert out == "contradiction"


# ---------------------------------------------------------------------------
# Topic clustering
# ---------------------------------------------------------------------------


def test_cluster_topic_default_known_label():
    cid, label = cluster_topic_v8(
        "Цифровой профиль и ruID", DEFAULT_TOPIC_CLUSTERS
    )
    assert cid != "T00"
    assert "ruid" in label.lower() or "цифров" in label.lower()


def test_cluster_topic_eaeu():
    cid, label = cluster_topic_v8("ЕАЭС и условия трудовой деятельности",
                                  DEFAULT_TOPIC_CLUSTERS)
    assert "еаэс" in label.lower()


def test_cluster_topic_unknown_returns_t00():
    cid, label = cluster_topic_v8("совершенно левая тема xyz",
                                  DEFAULT_TOPIC_CLUSTERS)
    assert cid == "T00"


def test_cluster_topic_handles_empty_string():
    cid, label = cluster_topic_v8("", DEFAULT_TOPIC_CLUSTERS)
    assert cid == "T00"


# ---------------------------------------------------------------------------
# Amendment graph → outdated detection
# ---------------------------------------------------------------------------


def test_outdated_detected_when_old_doc_amended_by_new():
    graph = {"D24": ["D11"]}  # D24 amends D11
    assert derive_outdated(graph, "D11", "D24") is True
    assert derive_outdated(graph, "D24", "D11") is True


def test_outdated_false_for_unrelated_pair():
    graph = {"D24": ["D11"]}
    assert derive_outdated(graph, "D04", "D26") is False


def test_outdated_handles_chained_amendments():
    """ПП 468 amends ПП 1510 (already amended by 1562)."""
    graph = {"D22": ["D21"], "D23": ["D21", "D22"]}
    assert derive_outdated(graph, "D21", "D23") is True
    assert derive_outdated(graph, "D22", "D23") is True


# ---------------------------------------------------------------------------
# Bundle schema
# ---------------------------------------------------------------------------


def test_bundle_schema_has_required_top_level_keys():
    bundle = build_forensic_bundle(
        documents=[
            {"id": "D01", "code": "FZ_115", "rank": 1, "title": "115-ФЗ", "type": "law"},
            {"id": "D02", "code": "ANALYTIC", "rank": 3, "title": "ВЦИОМ", "type": "analytic"},
        ],
        pairs=[],
        events=[],
        amendment_graph={},
    )
    for key in (
        "schema_version",
        "generated_at",
        "documents",
        "pairs",
        "topic_clusters",
        "amendment_graph",
        "status_scale",
        "status_distribution_pairs",
        "rank_pair_distribution",
        "control_numbers",
    ):
        assert key in bundle, f"missing key {key!r}"


def test_bundle_schema_version_is_v8_0():
    bundle = build_forensic_bundle(documents=[], pairs=[], events=[], amendment_graph={})
    assert bundle["schema_version"] == "v8.0"


def test_bundle_status_distribution_matches_pair_count():
    docs = [
        {"id": f"D{i:02d}", "code": f"DOC{i}", "rank": 1, "title": f"d{i}", "type": "law"}
        for i in range(1, 5)
    ]
    pairs = [
        # 4 docs → C(4,2) = 6 pairs
        {"id": "P1", "left": "D01", "right": "D02", "events": [_ev("same")]},
        {"id": "P2", "left": "D01", "right": "D03", "events": [_ev("same")]},
        {"id": "P3", "left": "D01", "right": "D04", "events": [_ev("partial")]},
        {"id": "P4", "left": "D02", "right": "D03", "events": [_ev("contradicts","high")]},
        {"id": "P5", "left": "D02", "right": "D04", "events": []},
        {"id": "P6", "left": "D03", "right": "D04", "events": [_ev("manual_review")]},
    ]
    bundle = build_forensic_bundle(
        documents=docs, pairs=pairs, events=[], amendment_graph={}
    )
    total = sum(bundle["status_distribution_pairs"].values())
    assert total == len(pairs)


def test_bundle_rank_pair_distribution_uses_normalised_keys():
    docs = [
        {"id": "D01", "code": "C1", "rank": 1, "title": "n", "type": "law"},
        {"id": "D02", "code": "C2", "rank": 3, "title": "n", "type": "analytic"},
    ]
    bundle = build_forensic_bundle(
        documents=docs,
        pairs=[{"id": "P1", "left": "D01", "right": "D02", "events": []}],
        events=[],
        amendment_graph={},
    )
    keys = bundle["rank_pair_distribution"]
    # Distribution key must be sorted lo↔hi rank for stable aggregation
    assert "1↔3" in keys or "3↔1" in keys


# ---------------------------------------------------------------------------
# Integration: replay the migration_v8 pipeline shape against the new module
# ---------------------------------------------------------------------------


def test_known_invariant_v7_v8_status_distribution_smoke():
    """Smoke test: a small synthetic batch with the v7 ratio shape (3 rank3,
    3 rank1) reaches manual_review/match/partial/not_comparable correctly."""
    docs = [
        {"id": "L1", "code": "L1", "rank": 1, "title": "Law 1", "type": "law"},
        {"id": "L2", "code": "L2", "rank": 1, "title": "Law 2", "type": "law"},
        {"id": "L3", "code": "L3", "rank": 1, "title": "Law 3", "type": "law"},
        {"id": "A1", "code": "A1", "rank": 3, "title": "Analytic 1", "type": "analytic"},
        {"id": "A2", "code": "A2", "rank": 3, "title": "Analytic 2", "type": "analytic"},
        {"id": "A3", "code": "A3", "rank": 3, "title": "Analytic 3", "type": "analytic"},
    ]
    pairs = [
        # rank1↔rank1 should follow events
        {"id": "P_LL_match", "left": "L1", "right": "L2", "events": [_ev("same")]},
        {"id": "P_LL_partial", "left": "L1", "right": "L3", "events": [_ev("partial")]},
        # rank3↔rank1 must be manual_review
        {"id": "P_AL_manual", "left": "A1", "right": "L1", "events": [_ev("same")]},
        # rank3↔rank3 follows events normally (no invariant)
        {"id": "P_AA_partial", "left": "A1", "right": "A2", "events": [_ev("partial")]},
        # empty events → not_comparable
        {"id": "P_NC", "left": "A2", "right": "A3", "events": []},
    ]
    bundle = build_forensic_bundle(documents=docs, pairs=pairs, events=[], amendment_graph={})
    statuses = {p["id"]: p["v8_status"] for p in bundle["pairs"]}
    assert statuses["P_LL_match"] == "match"
    assert statuses["P_LL_partial"] == "partial_overlap"
    assert statuses["P_AL_manual"] == "manual_review"
    assert statuses["P_AA_partial"] == "partial_overlap"
    assert statuses["P_NC"] == "not_comparable"


def test_aggregate_all_not_comparable_events_returns_not_comparable():
    """Line-212 path: events that all normalise to STATUS_NC (not_comparable)
    pass through every positive check and fall to the final `return STATUS_NC`."""
    out = aggregate_pair_status_v8(
        [{"status": "not_comparable"}, {"status": "not_comparable"}],
        left_rank=1, right_rank=1,
    )
    assert out == "not_comparable"


def test_aggregate_mixed_nc_and_match_events_returns_not_comparable():
    """Mixed not_comparable + match events: not all match → STATUS_NC."""
    out = aggregate_pair_status_v8(
        [{"status": "match"}, {"status": "not_comparable"}],
        left_rank=2, right_rank=2,
    )
    assert out == "not_comparable"


# ---------------------------------------------------------------------------
# Step 1 — explanation_short threading
# ---------------------------------------------------------------------------


def _docs_pair():
    return (
        [
            {"id": "D1", "code": "C1", "rank": 1, "title": "t1", "type": "law"},
            {"id": "D2", "code": "C2", "rank": 1, "title": "t2", "type": "law"},
        ],
        [{"id": "P1", "left": "D1", "right": "D2", "events": []}],
    )


def test_explanations_threaded_from_events():
    docs, pairs = _docs_pair()
    pairs[0]["events"] = [{"status": "same", "explanation_short": "Нормы совпадают"}]
    b = build_forensic_bundle(documents=docs, pairs=pairs, events=[], amendment_graph={})
    assert "Нормы совпадают" in b["pairs"][0]["explanations"]


def test_explanations_deduped_and_sorted():
    docs, pairs = _docs_pair()
    pairs[0]["events"] = [
        {"status": "same", "explanation_short": "Бета"},
        {"status": "partial", "explanation_short": "Альфа"},
        {"status": "same", "explanation_short": "Бета"},  # duplicate
    ]
    b = build_forensic_bundle(documents=docs, pairs=pairs, events=[], amendment_graph={})
    explanations = b["pairs"][0]["explanations"]
    assert explanations == sorted(set(explanations))
    assert len(explanations) == 2


def test_explanations_empty_when_no_event_has_it():
    docs, pairs = _docs_pair()
    pairs[0]["events"] = [{"status": "same"}]  # no explanation_short
    b = build_forensic_bundle(documents=docs, pairs=pairs, events=[], amendment_graph={})
    assert b["pairs"][0]["explanations"] == []
