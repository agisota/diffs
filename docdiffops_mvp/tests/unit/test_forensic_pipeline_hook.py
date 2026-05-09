"""Test the pipeline → forensic v8 translator + renderer composition.

These tests exercise the public surface DocDiffOps's pipeline relies on:
``forensic.bundle_from_batch_state`` (state translation) plus the four
``forensic_render`` writers, without importing ``pipeline.py`` itself
(which pulls heavy PyMuPDF/rapidfuzz deps not relevant to this contract).

If you change the pipeline's translation logic, these tests must follow.
"""
from __future__ import annotations

import json
from pathlib import Path

from docdiffops.forensic import bundle_from_batch_state
from docdiffops.forensic_render import (
    render_v8_docx_explanatory,
    render_v8_docx_redgreen,
    render_v8_pdf_summary,
    render_v8_xlsx,
)


def _state():
    return {
        "batch_id": "BATCH_TEST_001",
        "documents": [
            {"doc_id": "D1", "filename": "fz_115.html", "source_rank": 1,
             "doc_type": "LEGAL_NPA", "source_url": "https://kremlin.ru/x"},
            {"doc_id": "D2", "filename": "fz_109.html", "source_rank": 1,
             "doc_type": "LEGAL_NPA", "source_url": "https://kremlin.ru/y"},
            {"doc_id": "D3", "filename": "vciom.pdf", "source_rank": 3,
             "doc_type": "PRESENTATION", "source_url": ""},
        ],
        "artifacts": [],
    }


def _pairs():
    return [
        {"pair_id": "P1", "lhs_doc_id": "D1", "rhs_doc_id": "D2"},
        {"pair_id": "P2", "lhs_doc_id": "D1", "rhs_doc_id": "D3"},  # rank3↔rank1
        {"pair_id": "P3", "lhs_doc_id": "D2", "rhs_doc_id": "D3"},  # rank3↔rank1, no events
    ]


def _events():
    return [
        {"pair_id": "P1", "status": "partial", "severity": "medium",
         "topic": "Цифровой профиль и ruID"},
        {"pair_id": "P2", "status": "same", "topic": ""},
    ]


def test_state_translator_preserves_rank_invariant():
    bundle = bundle_from_batch_state(_state(), _events(), _pairs())
    statuses = {p["id"]: p["v8_status"] for p in bundle["pairs"]}
    # P1: rank1↔rank1 with partial → partial_overlap
    assert statuses["P1"] == "partial_overlap", statuses
    # P2: rank3↔rank1 with same → must be manual_review
    assert statuses["P2"] == "manual_review"
    # P3: rank3↔rank1 with no events → not_comparable
    assert statuses["P3"] == "not_comparable"


def test_state_translator_maps_doc_metadata():
    bundle = bundle_from_batch_state(_state(), _events(), _pairs())
    docs = {d["id"]: d for d in bundle["documents"]}
    assert docs["D1"]["rank"] == 1
    assert docs["D3"]["rank"] == 3
    assert docs["D1"]["title"] == "fz_115.html"
    assert docs["D3"]["type"] == "PRESENTATION"


def test_state_translator_handles_amendment_graph():
    state = _state()
    state["amendment_graph"] = {"D1": ["D2"]}  # D1 amends D2
    bundle = bundle_from_batch_state(state, _events(), _pairs())
    statuses = {p["id"]: p["v8_status"] for p in bundle["pairs"]}
    # P1 (D1↔D2) had partial → demoted to outdated by amendment graph
    assert statuses["P1"] == "outdated"


def test_state_translator_honors_known_contradictions():
    state = _state()
    state["known_contradictions"] = [["D1", "D2"]]
    bundle = bundle_from_batch_state(state, _events(), _pairs())
    statuses = {p["id"]: p["v8_status"] for p in bundle["pairs"]}
    assert statuses["P1"] == "contradiction"


def test_pipeline_composition_writes_all_five_artifacts(tmp_path: Path):
    """End-to-end: translate state → bundle → render four artifacts + JSON."""
    bundle = bundle_from_batch_state(_state(), _events(), _pairs())
    base = tmp_path / "forensic_v8"
    base.mkdir(parents=True)

    (base / "bundle.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    render_v8_xlsx(bundle, base / "forensic_v8.xlsx")
    render_v8_docx_explanatory(bundle, base / "forensic_v8_explanatory.docx")
    render_v8_docx_redgreen(bundle, base / "forensic_v8_redgreen.docx")
    render_v8_pdf_summary(bundle, base / "forensic_v8_summary.pdf")

    for name in (
        "bundle.json", "forensic_v8.xlsx",
        "forensic_v8_explanatory.docx", "forensic_v8_redgreen.docx",
        "forensic_v8_summary.pdf",
    ):
        p = base / name
        assert p.exists(), f"missing {name}"
        assert p.stat().st_size > 1000, f"{name} too small: {p.stat().st_size}b"

    # Schema sanity-check
    bundle2 = json.loads((base / "bundle.json").read_text(encoding="utf-8"))
    assert bundle2["schema_version"] == "v8.0"
    assert bundle2["control_numbers"]["documents"] == 3
    assert bundle2["control_numbers"]["pairs"] == 3


def test_state_translator_handles_empty_batch():
    bundle = bundle_from_batch_state({"documents": []}, [], [])
    assert bundle["control_numbers"]["documents"] == 0
    assert bundle["control_numbers"]["pairs"] == 0
    assert bundle["status_distribution_pairs"] == {}
    assert bundle["schema_version"] == "v8.0"


def test_pipeline_translator_output_passes_schema_validation():
    """Whatever DocDiffOps state shape pipeline gets, the resulting v8 bundle
    must validate against the JSON Schema (otherwise downstream renderers fail).
    """
    from docdiffops.forensic_schema import validate_bundle

    bundle = bundle_from_batch_state(_state(), _events(), _pairs())
    errors = validate_bundle(bundle)
    assert errors == [], f"unexpected schema errors: {errors[:3]}"


def test_empty_pipeline_bundle_passes_schema_validation():
    from docdiffops.forensic_schema import validate_bundle

    bundle = bundle_from_batch_state({"documents": []}, [], [])
    assert validate_bundle(bundle) == []
