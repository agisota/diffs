"""FastAPI integration tests for forensic v8 endpoints.

Uses TestClient with monkeypatched batch_dir so all file I/O goes to tmp_path.
READ_FROM_DB=false ensures JSON-only state reads (no Postgres needed).

fitz (PyMuPDF) is not in the test venv; stub it before importing the app so
the import chain (main → worker → pipeline → extract) doesn't crash.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Stub heavy native deps not installed in the test venv so the import
# chain (main → worker → pipeline → extract) resolves without errors.
_STUBS = [
    "fitz", "bs4", "bs4.element",
    "pptx", "pptx.util",
    "rapidfuzz", "rapidfuzz.fuzz",
    "sklearn", "sklearn.feature_extraction", "sklearn.feature_extraction.text",
]
for _m in _STUBS:
    sys.modules.setdefault(_m, MagicMock())

import pytest
from fastapi.testclient import TestClient

from docdiffops.forensic import build_forensic_bundle
from docdiffops.main import app


def _make_bundle() -> dict:
    docs = [
        {"id": "D1", "code": "C1", "rank": 1, "title": "t1", "type": "law"},
        {"id": "D2", "code": "C2", "rank": 1, "title": "t2", "type": "law"},
    ]
    pairs = [{"id": "P1", "left": "D1", "right": "D2",
              "events": [{"status": "same"}]}]
    return build_forensic_bundle(documents=docs, pairs=pairs, events=[], amendment_graph={})


def _write_batch(tmp_path: Path, batch_id: str, bundle: dict | None = None) -> Path:
    batch = tmp_path / "batches" / batch_id
    forensic_dir = batch / "reports" / "forensic_v8"
    forensic_dir.mkdir(parents=True, exist_ok=True)
    state = {"batch_id": batch_id, "documents": [], "artifacts": []}
    (batch / "state.json").write_text(json.dumps(state), encoding="utf-8")
    if bundle is not None:
        (forensic_dir / "bundle.json").write_text(
            json.dumps(bundle, ensure_ascii=False), encoding="utf-8"
        )
        # Create stub artifacts so kind endpoints can serve them.
        for name in ("forensic_v8.xlsx", "forensic_v8_explanatory.docx",
                     "forensic_v8_redgreen.docx", "forensic_v8_summary.pdf"):
            (forensic_dir / name).write_bytes(b"stub")
    return batch


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("READ_FROM_DB", "false")
    monkeypatch.setattr("docdiffops.main.batch_dir", lambda bid: tmp_path / "batches" / bid)
    monkeypatch.setattr("docdiffops.state.DATA_DIR", tmp_path)
    return TestClient(app)


@pytest.fixture()
def batch_with_bundle(tmp_path: Path):
    b = _make_bundle()
    _write_batch(tmp_path, "B001", bundle=b)
    return tmp_path, "B001", b


def test_get_forensic_returns_bundle_json(client, batch_with_bundle, tmp_path):
    _, batch_id, original = batch_with_bundle
    r = client.get(f"/batches/{batch_id}/forensic")
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == original["schema_version"]


def test_get_forensic_404_when_not_generated(client, tmp_path):
    _write_batch(tmp_path, "B002", bundle=None)  # no bundle.json
    r = client.get("/batches/B002/forensic")
    assert r.status_code == 404


def test_get_forensic_kind_xlsx(client, batch_with_bundle, tmp_path):
    _, batch_id, _ = batch_with_bundle
    r = client.get(f"/batches/{batch_id}/forensic/xlsx")
    assert r.status_code == 200


def test_get_forensic_kind_pdf(client, batch_with_bundle, tmp_path):
    _, batch_id, _ = batch_with_bundle
    r = client.get(f"/batches/{batch_id}/forensic/pdf")
    assert r.status_code == 200


def test_get_forensic_kind_redgreen_docx(client, batch_with_bundle, tmp_path):
    _, batch_id, _ = batch_with_bundle
    r = client.get(f"/batches/{batch_id}/forensic/redgreen_docx")
    assert r.status_code == 200


def test_get_forensic_kind_invalid_returns_400(client, batch_with_bundle, tmp_path):
    _, batch_id, _ = batch_with_bundle
    r = client.get(f"/batches/{batch_id}/forensic/badkind")
    assert r.status_code == 400
    assert "unknown kind" in r.json()["detail"]


def test_get_forensic_compare_returns_delta(client, tmp_path):
    old_b = _make_bundle()
    docs = [
        {"id": "D1", "code": "C1", "rank": 1, "title": "t1", "type": "law"},
        {"id": "D2", "code": "C2", "rank": 1, "title": "t2", "type": "law"},
    ]
    pairs_new = [{"id": "P1", "left": "D1", "right": "D2",
                  "events": [{"status": "contradicts"}]}]
    new_b = build_forensic_bundle(documents=docs, pairs=pairs_new,
                                  events=[], amendment_graph={})
    _write_batch(tmp_path, "OLD", bundle=old_b)
    _write_batch(tmp_path, "NEW", bundle=new_b)

    r = client.get("/batches/OLD/forensic/compare/NEW")
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == "v8-delta"
    assert body["control_numbers"]["pairs_changed"] == 1


def test_get_forensic_compare_404_when_bundle_missing(client, tmp_path):
    _write_batch(tmp_path, "OLD2", bundle=_make_bundle())
    # NEW2 has no bundle.json
    _write_batch(tmp_path, "NEW2", bundle=None)
    r = client.get("/batches/OLD2/forensic/compare/NEW2")
    assert r.status_code == 404


def test_get_forensic_compare_persist_writes_artifact(client, tmp_path):
    """persist=true saves delta to disk and registers it as a batch artifact."""
    old_b = _make_bundle()
    docs = [
        {"id": "D1", "code": "C1", "rank": 1, "title": "t1", "type": "law"},
        {"id": "D2", "code": "C2", "rank": 1, "title": "t2", "type": "law"},
    ]
    pairs_new = [{"id": "P1", "left": "D1", "right": "D2",
                  "events": [{"status": "contradicts"}]}]
    new_b = build_forensic_bundle(documents=docs, pairs=pairs_new,
                                  events=[], amendment_graph={})
    _write_batch(tmp_path, "BL", bundle=old_b)
    _write_batch(tmp_path, "CR", bundle=new_b)

    r = client.get("/batches/BL/forensic/compare/CR?persist=true")
    assert r.status_code == 200

    delta_path = tmp_path / "batches" / "CR" / "reports" / "forensic_v8" / "delta_from_BL.json"
    assert delta_path.exists()
    persisted = json.loads(delta_path.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == "v8-delta"

    # Delta is now visible in the batch's artifact list
    state = json.loads((tmp_path / "batches" / "CR" / "state.json").read_text(encoding="utf-8"))
    artifact_types = [a.get("type") for a in state.get("artifacts", [])]
    assert "forensic_delta" in artifact_types


def test_get_forensic_compare_artifacts_renders_xlsx_docx_pdf(client, tmp_path):
    """artifacts=true also renders xlsx/docx/pdf delta reports."""
    old_b = _make_bundle()
    docs = [
        {"id": "D1", "code": "C1", "rank": 1, "title": "t1", "type": "law"},
        {"id": "D2", "code": "C2", "rank": 1, "title": "t2", "type": "law"},
    ]
    new_b = build_forensic_bundle(
        documents=docs,
        pairs=[{"id": "P1", "left": "D1", "right": "D2",
                "events": [{"status": "contradicts"}]}],
        events=[], amendment_graph={},
    )
    _write_batch(tmp_path, "OLD3", bundle=old_b)
    _write_batch(tmp_path, "NEW3", bundle=new_b)

    r = client.get("/batches/OLD3/forensic/compare/NEW3?artifacts=true")
    assert r.status_code == 200

    base = tmp_path / "batches" / "NEW3" / "reports" / "forensic_v8"
    assert (base / "delta_from_OLD3.json").exists()
    assert (base / "delta_from_OLD3.xlsx").exists()
    assert (base / "delta_from_OLD3.docx").exists()
    assert (base / "delta_from_OLD3.pdf").exists()

    state = json.loads((tmp_path / "batches" / "NEW3" / "state.json").read_text(encoding="utf-8"))
    artifact_types = {a.get("type") for a in state.get("artifacts", [])}
    assert artifact_types >= {
        "forensic_delta",
        "forensic_delta_xlsx",
        "forensic_delta_docx",
        "forensic_delta_pdf",
    }


def test_get_forensic_trend_returns_v8_trend(client, tmp_path):
    """/forensic/trend aggregates N bundles into a v8-trend report."""
    docs = [
        {"id": "D1", "code": "C1", "rank": 1, "title": "t1", "type": "law"},
        {"id": "D2", "code": "C2", "rank": 1, "title": "t2", "type": "law"},
    ]
    bad = build_forensic_bundle(
        documents=docs,
        pairs=[{"id": "P1", "left": "D1", "right": "D2",
                "events": [{"status": "contradicts"}]}],
        events=[], amendment_graph={},
    )
    good = build_forensic_bundle(
        documents=docs,
        pairs=[{"id": "P1", "left": "D1", "right": "D2",
                "events": [{"status": "same"}]}],
        events=[], amendment_graph={},
    )
    _write_batch(tmp_path, "T1", bundle=bad)
    _write_batch(tmp_path, "T2", bundle=good)

    r = client.get("/forensic/trend?ids=T1,T2")
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == "v8-trend"
    assert body["bundle_count"] == 2
    assert body["trend_direction"] == "improving"


def test_get_forensic_trend_404_when_bundle_missing(client, tmp_path):
    _write_batch(tmp_path, "T3", bundle=_make_bundle())
    _write_batch(tmp_path, "T4", bundle=None)
    r = client.get("/forensic/trend?ids=T3,T4")
    assert r.status_code == 404


def test_get_forensic_trend_400_when_ids_empty(client, tmp_path):
    r = client.get("/forensic/trend?ids=")
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# v10 bundle endpoint tests
# ---------------------------------------------------------------------------

_V10_FILENAMES = [
    "correlation_matrix.csv",
    "dependency_graph.csv",
    "claim_provenance.csv",
    "coverage_heatmap.csv",
    "Интегральное_перекрестное_сравнение_v10.xlsx",
    "Пояснительная_записка_v10.docx",
    "Пояснительная_записка_v10.pdf",
    "Интегральное_перекрестное_сравнение_v10.pdf",
]


@pytest.fixture()
def batch_with_v10(tmp_path: Path, client):
    """Create a batch and manually populate reports/v10/ with dummy files."""
    r = client.post("/batches", json={"title": "v10 test batch"})
    assert r.status_code == 200
    batch_id = r.json()["batch_id"]
    base = tmp_path / "batches" / batch_id / "reports" / "v10"
    base.mkdir(parents=True, exist_ok=True)
    for fname in _V10_FILENAMES:
        (base / fname).write_bytes(b"dummy")
    return batch_id


def test_v10_endpoint_404_when_no_artifacts(client, tmp_path):
    """GET /forensic/v10 returns 404 when v10 dir is absent."""
    r = client.post("/batches", json={"title": "no v10"})
    assert r.status_code == 200
    batch_id = r.json()["batch_id"]
    r2 = client.get(f"/batches/{batch_id}/forensic/v10")
    assert r2.status_code == 404
    assert "v10 bundle not generated" in r2.json()["detail"]


def test_v10_endpoint_returns_8_urls_when_artifacts_present(client, batch_with_v10):
    """GET /forensic/v10 returns JSON with 8 artifact URL keys."""
    batch_id = batch_with_v10
    r = client.get(f"/batches/{batch_id}/forensic/v10")
    assert r.status_code == 200
    body = r.json()
    assert body["batch_id"] == batch_id
    assert len(body["artifacts"]) == 8
    expected_keys = {
        "xlsx", "note_docx", "note_pdf", "integral_matrix_pdf",
        "correlation_matrix_csv", "dependency_graph_csv",
        "claim_provenance_csv", "coverage_heatmap_csv",
    }
    assert set(body["artifacts"].keys()) == expected_keys


def test_download_xlsx_v10(client, batch_with_v10):
    """GET /forensic/xlsx_v10 serves the v10 XLSX file."""
    r = client.get(f"/batches/{batch_with_v10}/forensic/xlsx_v10")
    assert r.status_code == 200


def test_download_note_docx(client, batch_with_v10):
    """GET /forensic/note_docx serves the v10 explanatory note DOCX."""
    r = client.get(f"/batches/{batch_with_v10}/forensic/note_docx")
    assert r.status_code == 200


def test_download_note_pdf(client, batch_with_v10):
    """GET /forensic/note_pdf serves the v10 explanatory note PDF."""
    r = client.get(f"/batches/{batch_with_v10}/forensic/note_pdf")
    assert r.status_code == 200


def test_download_integral_matrix_pdf(client, batch_with_v10):
    """GET /forensic/integral_matrix_pdf serves the v10 integral matrix PDF."""
    r = client.get(f"/batches/{batch_with_v10}/forensic/integral_matrix_pdf")
    assert r.status_code == 200


def test_download_correlation_matrix_csv(client, batch_with_v10):
    """GET /forensic/correlation_matrix_csv serves the correlation matrix CSV."""
    r = client.get(f"/batches/{batch_with_v10}/forensic/correlation_matrix_csv")
    assert r.status_code == 200


def test_download_dependency_graph_csv(client, batch_with_v10):
    """GET /forensic/dependency_graph_csv serves the dependency graph CSV."""
    r = client.get(f"/batches/{batch_with_v10}/forensic/dependency_graph_csv")
    assert r.status_code == 200


def test_download_unknown_kind_400(client, batch_with_v10):
    """GET /forensic/foobar returns 400 with 'unknown kind' in detail."""
    r = client.get(f"/batches/{batch_with_v10}/forensic/foobar")
    assert r.status_code == 400
    assert "unknown kind" in r.json()["detail"]


def test_existing_v8_kinds_still_work(client, batch_with_bundle, tmp_path):
    """Existing v8 kind=json still returns 200 (backwards-compat)."""
    _, batch_id, _ = batch_with_bundle
    r = client.get(f"/batches/{batch_id}/forensic/json")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# v10.zip bundle endpoint tests  (PR-7.1)
# ---------------------------------------------------------------------------


def test_v10_zip_404_when_no_artifacts(client):
    """GET /forensic/v10.zip returns 404 when no v10 dir exists at all."""
    r = client.post("/batches", json={"title": "no v10 zip test"})
    assert r.status_code == 200
    batch_id = r.json()["batch_id"]
    r2 = client.get(f"/batches/{batch_id}/forensic/v10.zip")
    assert r2.status_code == 404
    assert "v10 bundle not generated" in r2.json()["detail"]


def test_v10_zip_200_when_complete(client, batch_with_v10):
    """GET /forensic/v10.zip returns 200 with correct content-type and disposition."""
    r = client.get(f"/batches/{batch_with_v10}/forensic/v10.zip")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    cd = r.headers.get("content-disposition", "")
    assert "forensic_v10_" in cd
    assert batch_with_v10 in cd


def test_v10_zip_contains_all_8_files(client, batch_with_v10):
    """ZIP response body contains exactly the 8 expected filenames."""
    import io as _io
    import zipfile as _zf

    r = client.get(f"/batches/{batch_with_v10}/forensic/v10.zip")
    assert r.status_code == 200

    with _zf.ZipFile(_io.BytesIO(r.content)) as zf:
        names = set(zf.namelist())

    expected = {
        "Интегральное_перекрестное_сравнение_v10.xlsx",
        "Пояснительная_записка_v10.docx",
        "Пояснительная_записка_v10.pdf",
        "Интегральное_перекрестное_сравнение_v10.pdf",
        "correlation_matrix.csv",
        "dependency_graph.csv",
        "claim_provenance.csv",
        "coverage_heatmap.csv",
    }
    assert len(names) == 8
    assert names == expected


def test_v10_zip_404_when_partial(client, tmp_path):
    """GET /forensic/v10.zip returns 404 when only some v10 files exist."""
    r = client.post("/batches", json={"title": "partial v10 zip test"})
    assert r.status_code == 200
    batch_id = r.json()["batch_id"]

    # Create v10 dir but only populate 5 of the 8 required files
    base = tmp_path / "batches" / batch_id / "reports" / "v10"
    base.mkdir(parents=True, exist_ok=True)
    partial_files = [
        "correlation_matrix.csv",
        "dependency_graph.csv",
        "claim_provenance.csv",
        "coverage_heatmap.csv",
        "Интегральное_перекрестное_сравнение_v10.xlsx",
    ]
    for fname in partial_files:
        (base / fname).write_bytes(b"dummy")

    r2 = client.get(f"/batches/{batch_id}/forensic/v10.zip")
    assert r2.status_code == 404
    assert "missing" in r2.json()["detail"]
