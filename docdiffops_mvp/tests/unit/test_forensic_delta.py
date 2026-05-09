"""Tests for forensic_delta.compare_bundles — delta comparison contract."""
from __future__ import annotations

import pytest

from docdiffops.forensic import build_forensic_bundle
from docdiffops.forensic_delta import (
    ACTIONS_COVERAGE_NEITHER,
    ACTIONS_COVERAGE_NEW_ONLY,
    ACTIONS_COVERAGE_OLD_ONLY,
    ACTIONS_COVERAGE_SYMMETRIC,
    DIRECTION_DEGRADED,
    DIRECTION_IMPROVED,
    DIRECTION_UNCHANGED,
    STATUS_RANK,
    compare_bundles,
)


def _bundle(pairs_statuses: dict[str, str]) -> dict:
    """Minimal valid v8 bundle with specified pair statuses."""
    docs = [
        {"id": "D1", "code": "C1", "rank": 1, "title": "t1", "type": "law"},
        {"id": "D2", "code": "C2", "rank": 1, "title": "t2", "type": "law"},
        {"id": "D3", "code": "C3", "rank": 1, "title": "t3", "type": "law"},
    ]
    pairs = [
        {"id": pid, "left": "D1", "right": "D2",
         "events": [{"status": st}]}
        for pid, st in pairs_statuses.items()
    ]
    return build_forensic_bundle(documents=docs, pairs=pairs,
                                 events=[], amendment_graph={})


def test_identical_bundles_produce_zero_changes():
    b = _bundle({"P1": "same", "P2": "partial"})
    d = compare_bundles(b, b)
    assert d["control_numbers"]["pairs_changed"] == 0
    assert d["status_changes"] == []
    assert d["distribution_diff"] == {}


def test_status_improvement_detected():
    old = _bundle({"P1": "contradicts"})
    new = _bundle({"P1": "partial"})
    d = compare_bundles(old, new)
    assert d["control_numbers"]["pairs_changed"] == 1
    change = d["status_changes"][0]
    assert change["pair_id"] == "P1"
    assert change["old_status"] == "contradiction"
    assert change["new_status"] == "partial_overlap"
    assert change["direction"] == DIRECTION_IMPROVED


def test_status_regression_detected():
    old = _bundle({"P1": "same"})
    new = _bundle({"P1": "contradicts"})
    d = compare_bundles(old, new)
    assert d["control_numbers"]["pairs_changed"] == 1
    assert d["status_changes"][0]["direction"] == DIRECTION_DEGRADED


def test_new_pair_in_second_bundle():
    old = _bundle({"P1": "same"})
    new = _bundle({"P1": "same", "P2": "partial"})
    d = compare_bundles(old, new)
    assert d["control_numbers"]["pairs_new"] == 1
    assert any(p["id"] == "P2" for p in d["new_pairs"])


def test_removed_pair_in_second_bundle():
    old = _bundle({"P1": "same", "P2": "partial"})
    new = _bundle({"P1": "same"})
    d = compare_bundles(old, new)
    assert d["control_numbers"]["pairs_removed"] == 1
    assert any(p["id"] == "P2" for p in d["removed_pairs"])


def test_distribution_diff_correct():
    old = _bundle({"P1": "same", "P2": "contradicts"})
    new = _bundle({"P1": "same", "P2": "partial"})
    d = compare_bundles(old, new)
    # contradiction goes down by 1, partial_overlap goes up by 1
    assert d["distribution_diff"].get("contradiction", 0) == -1
    assert d["distribution_diff"].get("partial_overlap", 0) == 1


def test_direction_enum_uses_status_rank_ordering():
    ordered = ["match", "partial_overlap", "outdated", "manual_review",
               "source_gap", "contradiction", "not_comparable"]
    for i, hi in enumerate(ordered):
        for lo in ordered[i + 1:]:
            assert STATUS_RANK[hi] > STATUS_RANK[lo], \
                f"Expected {hi!r} > {lo!r} in STATUS_RANK"


def test_schema_version_is_v8_delta():
    b = _bundle({"P1": "same"})
    d = compare_bundles(b, b)
    assert d["schema_version"] == "v8-delta"


def test_control_numbers_are_correct():
    old = _bundle({"P1": "same", "P2": "contradicts"})
    new = _bundle({"P1": "partial", "P3": "same"})
    d = compare_bundles(old, new)
    cn = d["control_numbers"]
    assert cn["pairs_total"] == 3      # P1, P2, P3
    assert cn["pairs_changed"] == 1    # P1 changed
    assert cn["pairs_new"] == 1        # P3
    assert cn["pairs_removed"] == 1    # P2


def test_resolved_pairs_counted():
    old = _bundle({"P1": "contradicts", "P2": "partial"})
    new = _bundle({"P1": "same", "P2": "same"})
    d = compare_bundles(old, new)
    assert d["control_numbers"]["pairs_resolved"] == 2


def test_not_comparable_to_match_is_improved():
    # STATUS_RANK: match=6 > not_comparable=0 → improved
    old = _bundle({"P1": "partial"})  # will become not_comparable (no events for "none")
    # Build manually to force not_comparable
    docs = [{"id": "D1", "code": "C", "rank": 1, "title": "t", "type": "law"},
            {"id": "D2", "code": "C2", "rank": 1, "title": "t2", "type": "law"}]
    old_b = build_forensic_bundle(
        documents=docs,
        pairs=[{"id": "P1", "left": "D1", "right": "D2", "events": []}],
        events=[], amendment_graph={},
    )
    new_b = build_forensic_bundle(
        documents=docs,
        pairs=[{"id": "P1", "left": "D1", "right": "D2",
                "events": [{"status": "same"}]}],
        events=[], amendment_graph={},
    )
    d = compare_bundles(old_b, new_b)
    assert d["status_changes"][0]["direction"] == DIRECTION_IMPROVED


def test_schema_version_mismatch_raises_value_error():
    b = _bundle({"P1": "same"})
    bad = dict(b, schema_version="v7.0")
    with pytest.raises(ValueError, match="incompatible schema_version"):
        compare_bundles(bad, b)
    with pytest.raises(ValueError, match="incompatible schema_version"):
        compare_bundles(b, bad)


def test_empty_old_bundle_produces_all_new_pairs():
    old = build_forensic_bundle(documents=[], pairs=[], events=[], amendment_graph={})
    new = _bundle({"P1": "same", "P2": "partial"})
    d = compare_bundles(old, new)
    assert d["control_numbers"]["pairs_new"] == 2
    assert d["control_numbers"]["pairs_removed"] == 0


def test_empty_new_bundle_produces_all_removed_pairs():
    old = _bundle({"P1": "same", "P2": "partial"})
    new = build_forensic_bundle(documents=[], pairs=[], events=[], amendment_graph={})
    d = compare_bundles(old, new)
    assert d["control_numbers"]["pairs_removed"] == 2
    assert d["control_numbers"]["pairs_new"] == 0


def test_asymmetric_actions_coverage_sets_warning():
    old = _bundle({"P1": "same"})
    new = dict(_bundle({"P1": "same"}))
    new["actions_catalogue"] = []    # new has it, old doesn't
    d = compare_bundles(old, new)
    assert d["actions_coverage"] == ACTIONS_COVERAGE_NEW_ONLY
    assert d["asymmetric_actions_warning"] is not None
    assert "new" in d["asymmetric_actions_warning"]


def test_symmetric_actions_coverage():
    b = _bundle({"P1": "same"})
    b_with = dict(b, actions_catalogue=[])
    d = compare_bundles(b_with, b_with)
    assert d["actions_coverage"] == ACTIONS_COVERAGE_SYMMETRIC
    assert d["asymmetric_actions_warning"] is None


def test_neither_actions_coverage():
    b = _bundle({"P1": "same"})
    d = compare_bundles(b, b)
    assert d["actions_coverage"] == ACTIONS_COVERAGE_NEITHER
    assert d["asymmetric_actions_warning"] is None


def test_unchanged_pairs_not_in_status_changes():
    b = _bundle({"P1": "same", "P2": "partial", "P3": "contradicts"})
    d = compare_bundles(b, b)
    assert d["status_changes"] == []
    assert d["control_numbers"]["pairs_changed"] == 0
