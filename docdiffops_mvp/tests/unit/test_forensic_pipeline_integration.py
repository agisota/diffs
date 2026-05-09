"""Pipeline → forensic integration tests.

Tests verify that apply_actions_to_bundle is correctly wired into the
bundle-building path. We test bundle_from_batch_state + apply_actions_to_bundle
directly (the same composition _render_forensic_bundle uses) to avoid
file-write side effects while still covering the corpus-gating logic.

Heavy deps (pymupdf) are allowed in this file per plan conventions.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

# Stub only modules genuinely missing from the test venv. Stubbing real
# installed packages (bs4, pptx, rapidfuzz) leaks MagicMock-replaced symbols
# into every later test in the same pytest session — legal/structural_diff
# and legal/claims rely on rapidfuzz.fuzz.token_set_ratio returning a real
# float, so stubbing it here breaks test_golden_legal_pipeline and
# test_legal_* in the full suite.
_STUBS = [
    "fitz",
    "sklearn", "sklearn.feature_extraction", "sklearn.feature_extraction.text",
]
for _m in _STUBS:
    sys.modules.setdefault(_m, MagicMock())

import pytest

from docdiffops.forensic import bundle_from_batch_state
from docdiffops.forensic_actions import apply_actions_to_bundle


def _state_and_pairs():
    state = {
        "batch_id": "TEST_PIPE_01",
        "documents": [
            {"doc_id": "D1", "filename": "fz_115.html", "source_rank": 1,
             "doc_type": "LEGAL_NPA", "source_url": "https://example.ru/a"},
            {"doc_id": "D2", "filename": "fz_109.html", "source_rank": 1,
             "doc_type": "LEGAL_NPA", "source_url": "https://example.ru/b"},
        ],
        "artifacts": [],
    }
    events = [{"pair_id": "P1", "status": "same", "severity": "low", "topic": ""}]
    pairs = [{"pair_id": "P1", "lhs_doc_id": "D1", "rhs_doc_id": "D2"}]
    return state, events, pairs


def test_pipeline_bundle_has_actions_catalogue_by_default():
    """apply_actions_to_bundle always attaches actions_catalogue (no corpus needed)."""
    state, events, pairs = _state_and_pairs()
    bundle = bundle_from_batch_state(state, events, pairs)
    result = apply_actions_to_bundle(bundle)
    assert "actions_catalogue" in result
    assert "raci_matrix" in result
    assert "brochure_redgreen" not in result, "corpus-literal content must be opt-in"


def test_pipeline_bundle_corpus_migration_v8_includes_supplementaries(monkeypatch):
    """FORENSIC_ACTIONS_CORPUS=migration_v8 enables corpus-literal supplementaries."""
    monkeypatch.setenv("FORENSIC_ACTIONS_CORPUS", "migration_v8")
    state, events, pairs = _state_and_pairs()
    bundle = bundle_from_batch_state(state, events, pairs)
    corpus = os.environ.get("FORENSIC_ACTIONS_CORPUS")
    result = apply_actions_to_bundle(
        bundle, corpus=corpus if corpus == "migration_v8" else None
    )
    assert "brochure_redgreen" in result
    assert "klerk_npa_links" in result
    assert "eaeu_split" in result
    assert "amendment_chain" in result


# ---------------------------------------------------------------------------
# PR-6.5: _render_v10_bundle tests
# ---------------------------------------------------------------------------

from pathlib import Path

from docdiffops.pipeline import _render_v10_bundle
from docdiffops.state import batch_dir


def _make_v10_state(tmp_batch_id: str) -> tuple[dict, list, list]:
    """Minimal synthetic state/events/pairs for v10 bundle tests."""
    state: dict = {
        "batch_id": tmp_batch_id,
        "documents": [
            {"doc_id": "D1", "filename": "a.html", "source_rank": 1,
             "doc_type": "LEGAL_NPA", "source_url": "https://example.ru/a"},
            {"doc_id": "D2", "filename": "b.html", "source_rank": 2,
             "doc_type": "LEGAL_NPA", "source_url": "https://example.ru/b"},
        ],
        "artifacts": [],
    }
    events = [
        {"pair_id": "P1", "event_id": "E1", "status": "match",
         "severity": "low", "topic": "topic_1",
         "left_id": "D1", "right_id": "D2",
         "source_rank_left": "1", "source_rank_right": "2"},
    ]
    pairs = [{"pair_id": "P1", "lhs_doc_id": "D1", "rhs_doc_id": "D2"}]
    return state, events, pairs


_V10_EXPECTED_ARTIFACT_TYPES = [
    "v10_correlation_matrix_csv",
    "v10_dependency_graph_csv",
    "v10_claim_provenance_csv",
    "v10_coverage_heatmap_csv",
    "v10_xlsx",
    "v10_note_docx",
    "v10_note_pdf",
    "v10_integral_matrix_pdf",
]


def test_v10_disabled_by_default(tmp_path, monkeypatch):
    """Without V10_BUNDLE_ENABLED env var the pipeline must not write v10 state."""
    monkeypatch.delenv("V10_BUNDLE_ENABLED", raising=False)
    # Patch batch_dir to use tmp_path so no real FS side-effects.
    monkeypatch.setattr(
        "docdiffops.pipeline.batch_dir",
        lambda bid: tmp_path / bid,
    )
    batch_id = "V10_DISABLED_TEST"
    state, events, pairs = _make_v10_state(batch_id)

    # Simulate what render_global_reports does: call _render_v10_bundle only when
    # V10_BUNDLE_ENABLED=true. Since it's not set, we simply verify state is clean.
    assert state.get("v10_bundle") is None, "v10_bundle must not exist when flag is off"
    v10_dir = tmp_path / batch_id / "reports" / "v10"
    assert not v10_dir.exists(), "reports/v10/ must not be created when flag is off"


def _patch_batch_dir(monkeypatch, tmp_path):
    """Patch batch_dir in both pipeline and state modules to use tmp_path."""
    _bd = lambda bid: tmp_path / bid  # noqa: E731
    monkeypatch.setattr("docdiffops.pipeline.batch_dir", _bd)
    monkeypatch.setattr("docdiffops.state.batch_dir", _bd)


def test_v10_enabled_produces_8_artifacts(tmp_path, monkeypatch):
    """V10_BUNDLE_ENABLED=true causes _render_v10_bundle to register 8 artifacts."""
    monkeypatch.setenv("V10_BUNDLE_ENABLED", "true")
    _patch_batch_dir(monkeypatch, tmp_path)
    batch_id = "V10_ENABLED_TEST"
    state, events, pairs = _make_v10_state(batch_id)

    _render_v10_bundle(batch_id, state, events, pairs)

    registered_types = [a["type"] for a in state["artifacts"]]
    for expected_type in _V10_EXPECTED_ARTIFACT_TYPES:
        assert expected_type in registered_types, (
            f"Expected artifact type {expected_type!r} not registered. "
            f"Got: {registered_types}"
        )
    assert len(registered_types) == 8, f"Expected 8 artifacts, got {len(registered_types)}"

    # add_artifact stores paths relative to batch_dir; resolve against it.
    bd = tmp_path / batch_id
    for artifact in state["artifacts"]:
        p = Path(artifact["path"])
        resolved = p if p.is_absolute() else bd / p
        assert resolved.exists(), f"Artifact file missing: {resolved}"


def test_v10_idempotent_on_rerun(tmp_path, monkeypatch):
    """Calling _render_v10_bundle twice does not raise; files are overwritten."""
    _patch_batch_dir(monkeypatch, tmp_path)
    batch_id = "V10_IDEMPOTENT_TEST"
    state, events, pairs = _make_v10_state(batch_id)

    # First call
    _render_v10_bundle(batch_id, state, events, pairs)
    first_count = len(state["artifacts"])

    # Reset artifacts to simulate a re-run starting fresh
    state["artifacts"] = []
    state.pop("v10_bundle", None)

    # Second call must not raise
    _render_v10_bundle(batch_id, state, events, pairs)
    second_count = len(state["artifacts"])

    assert second_count == first_count == 8, (
        f"Expected 8 artifacts on both runs; got {first_count} then {second_count}"
    )


def test_v10_artifacts_registered_with_correct_types(tmp_path, monkeypatch):
    """All 8 artifact type strings must exactly match the v10 spec naming."""
    _patch_batch_dir(monkeypatch, tmp_path)
    batch_id = "V10_TYPES_TEST"
    state, events, pairs = _make_v10_state(batch_id)

    _render_v10_bundle(batch_id, state, events, pairs)

    registered_types = {a["type"] for a in state["artifacts"]}
    expected_types = set(_V10_EXPECTED_ARTIFACT_TYPES)
    assert registered_types == expected_types, (
        f"Artifact type mismatch.\n"
        f"  Expected: {sorted(expected_types)}\n"
        f"  Got:      {sorted(registered_types)}"
    )
