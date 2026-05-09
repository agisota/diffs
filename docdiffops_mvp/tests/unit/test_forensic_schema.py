"""Validate that the system always produces v8.0-conformant bundles."""
from __future__ import annotations

import pytest

from docdiffops.forensic import build_forensic_bundle
from docdiffops.forensic_actions import apply_actions_to_bundle
from docdiffops.forensic_schema import (
    BUNDLE_SCHEMA_DICT,
    V8_STATUS_ENUM,
    get_bundle_schema,
    validate_bundle,
)


def test_schema_dict_has_required_top_level():
    s = get_bundle_schema()
    assert s["title"].startswith("DocDiffOps Forensic v8")
    for k in ("schema_version", "documents", "pairs", "topic_clusters",
              "amendment_graph", "status_scale", "control_numbers"):
        assert k in s["required"]


def test_v8_status_enum_complete():
    assert set(V8_STATUS_ENUM) == {
        "match", "partial_overlap", "contradiction", "outdated",
        "source_gap", "manual_review", "not_comparable",
    }


def test_empty_bundle_validates():
    bundle = build_forensic_bundle(documents=[], pairs=[], events=[], amendment_graph={})
    errs = validate_bundle(bundle)
    assert errs == []


def test_smoke_bundle_validates():
    docs = [
        {"id": "D1", "code": "C1", "rank": 1, "title": "Doc 1", "type": "law"},
        {"id": "D2", "code": "C2", "rank": 3, "title": "Doc 2", "type": "analytic"},
    ]
    pairs = [
        {"id": "P1", "left": "D1", "right": "D2", "events": [{"status": "partial"}]},
    ]
    bundle = build_forensic_bundle(
        documents=docs, pairs=pairs, events=[], amendment_graph={"D1": ["D2"]}
    )
    errs = validate_bundle(bundle)
    assert errs == [], errs


def test_bundle_with_actions_still_validates():
    docs = [
        {"id": "D18", "code": "BR", "rank": 2, "title": "брошюра", "type": "brochure"},
        {"id": "D20", "code": "PP", "rank": 1, "title": "ПП 2573", "type": "law"},
    ]
    pairs = [{"id": "P1", "left": "D18", "right": "D20", "events": [{"status": "partial"}]}]
    bundle = build_forensic_bundle(documents=docs, pairs=pairs, events=[], amendment_graph={})
    enriched = apply_actions_to_bundle(bundle)
    errs = validate_bundle(enriched)
    assert errs == [], errs


def test_invalid_v8_status_is_rejected():
    bundle = {
        "schema_version": "v8.0", "generated_at": "2026-05-09 00:00:00Z",
        "documents": [], "pairs": [{"id": "P1", "left": "D1", "right": "D2",
                                    "v8_status": "WRONG_STATUS"}],
        "topic_clusters": [], "amendment_graph": {},
        "status_scale": V8_STATUS_ENUM,
        "status_distribution_pairs": {},
        "rank_pair_distribution": {},
        "control_numbers": {"documents": 0, "pairs": 1, "events": 0},
    }
    errs = validate_bundle(bundle)
    assert any("v8_status" in e for e in errs), errs


def test_missing_required_key_is_rejected():
    bundle = {"schema_version": "v8.0"}  # missing many required keys
    errs = validate_bundle(bundle)
    assert len(errs) >= 5


def test_invalid_schema_version_is_rejected():
    bundle = {
        "schema_version": "v7.0",  # bad
        "generated_at": "x", "documents": [], "pairs": [],
        "topic_clusters": [], "amendment_graph": {},
        "status_scale": V8_STATUS_ENUM,
        "status_distribution_pairs": {}, "rank_pair_distribution": {},
        "control_numbers": {"documents": 0, "pairs": 0, "events": 0},
    }
    errs = validate_bundle(bundle)
    assert any("schema_version" in e for e in errs)


def test_invalid_document_rank_is_rejected():
    bundle = {
        "schema_version": "v8.0", "generated_at": "x",
        "documents": [{"id": "D1", "code": "X", "rank": 99, "title": "x", "type": "x"}],
        "pairs": [], "topic_clusters": [], "amendment_graph": {},
        "status_scale": V8_STATUS_ENUM,
        "status_distribution_pairs": {}, "rank_pair_distribution": {},
        "control_numbers": {"documents": 1, "pairs": 0, "events": 0},
    }
    errs = validate_bundle(bundle)
    assert any("rank" in e for e in errs), errs


# ---------------------------------------------------------------------------
# _manual_validate fallback — exercises the ImportError branch in validate_bundle
# ---------------------------------------------------------------------------


def test_manual_validate_fallback_valid_bundle(monkeypatch):
    """When jsonschema is unavailable, _manual_validate is used; valid bundles pass."""
    import sys
    monkeypatch.setitem(sys.modules, "jsonschema", None)

    bundle = build_forensic_bundle(documents=[], pairs=[], events=[], amendment_graph={})
    errs = validate_bundle(bundle)
    assert errs == []


def test_manual_validate_fallback_bad_schema_version(monkeypatch):
    """_manual_validate catches wrong schema_version prefix."""
    import sys
    monkeypatch.setitem(sys.modules, "jsonschema", None)

    bundle = {
        "schema_version": "v9.0",
        "generated_at": "x", "documents": [], "pairs": [],
        "topic_clusters": [], "amendment_graph": {},
        "status_scale": V8_STATUS_ENUM,
        "status_distribution_pairs": {}, "rank_pair_distribution": {},
        "control_numbers": {"documents": 0, "pairs": 0, "events": 0},
    }
    errs = validate_bundle(bundle)
    assert any("schema_version" in e for e in errs), errs


def test_manual_validate_fallback_invalid_pair_status(monkeypatch):
    """_manual_validate catches invalid v8_status in pairs."""
    import sys
    monkeypatch.setitem(sys.modules, "jsonschema", None)

    bundle = {
        "schema_version": "v8.0",
        "generated_at": "x", "documents": [],
        "pairs": [{"id": "P1", "left": "D1", "right": "D2", "v8_status": "BOGUS"}],
        "topic_clusters": [], "amendment_graph": {},
        "status_scale": V8_STATUS_ENUM,
        "status_distribution_pairs": {}, "rank_pair_distribution": {},
        "control_numbers": {"documents": 0, "pairs": 1, "events": 0},
    }
    errs = validate_bundle(bundle)
    assert any("BOGUS" in e or "v8_status" in e for e in errs), errs


def test_manual_validate_fallback_missing_required_keys(monkeypatch):
    """_manual_validate reports missing required top-level keys."""
    import sys
    monkeypatch.setitem(sys.modules, "jsonschema", None)

    bundle = {"schema_version": "v8.0"}
    errs = validate_bundle(bundle)
    assert len(errs) >= 3, errs


def test_explanations_field_is_optional_and_validates():
    """pairs[].explanations is an optional string-list; bundle still validates."""
    docs = [
        {"id": "D1", "code": "C1", "rank": 1, "title": "t1", "type": "law"},
        {"id": "D2", "code": "C2", "rank": 1, "title": "t2", "type": "law"},
    ]
    pairs = [{"id": "P1", "left": "D1", "right": "D2",
              "events": [{"status": "same", "explanation_short": "Test"}]}]
    b = build_forensic_bundle(documents=docs, pairs=pairs, events=[], amendment_graph={})
    assert b["pairs"][0]["explanations"] == ["Test"]
    assert validate_bundle(b) == []


def test_legacy_v8_0_bundle_without_explanations_still_validates():
    """Backward compat: v8.0 bundles produced before the explanations addition
    must still validate as legitimate v8 bundles."""
    docs = [
        {"id": "D1", "code": "C1", "rank": 1, "title": "t1", "type": "law"},
        {"id": "D2", "code": "C2", "rank": 1, "title": "t2", "type": "law"},
    ]
    legacy_pair = {
        "id": "P1", "left": "D1", "right": "D2",
        "left_rank": 1, "right_rank": 1,
        "v8_status": "match", "events_count": 1, "topics": [],
        "rank_pair": "1—1",
        # NOTE: no "explanations" field — pre-v8.1 shape
    }
    legacy_bundle = {
        "schema_version": "v8.0",
        "generated_at": "2025-01-01T00:00:00Z",
        "documents": docs,
        "pairs": [legacy_pair],
        "topic_clusters": [],
        "amendment_graph": {},
        "known_contradictions": [],
        "status_scale": ["match", "partial_overlap", "contradiction",
                         "outdated", "source_gap", "manual_review", "not_comparable"],
        "status_distribution_pairs": {"match": 1},
        "rank_pair_distribution": {"1—1": 1},
        "control_numbers": {"documents": 2, "pairs": 1, "events": 0},
    }
    assert validate_bundle(legacy_bundle) == []
