"""End-to-end dual-write parity test (PR-1.2 carryover, lands in PR-1.3).

Goal: prove that the JSON state.json and the Postgres rows agree after a
real batch run. The test runs the FastAPI app via TestClient (no shelling
out to docker) and uses the compose ``db`` service for Postgres.

Skip behavior: if neither testcontainers nor a reachable DATABASE_URL is
available, the test SKIPs with a clear message rather than crashing.
This matches the constraint in §10 closures: 30-day retention, no PII,
no auth — and the practical observation that ``docker info`` may require
sudo on dev machines.

Marker: ``requires_compose_db`` — defined in ``pyproject.toml``.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_compose_db


# ---------------------------------------------------------------------------
# Database connection guard.
# ---------------------------------------------------------------------------


def _resolve_database_url() -> str | None:
    """Return a usable Postgres URL or None if we should SKIP.

    Order of preference:
    1. ``DATABASE_URL`` already set in env (e.g. compose-up Postgres).
    2. testcontainers Postgres (only attempted when DOCKER_HOST sockets work).
    3. None → SKIP.
    """
    url = os.getenv("DATABASE_URL")
    if url and url.startswith("postgresql"):
        return url
    # Attempt testcontainers; gracefully skip on any failure (sudo-only
    # docker, missing image, etc.).
    try:
        from testcontainers.postgres import PostgresContainer  # type: ignore
    except Exception:
        return None
    try:
        global _PG_CONTAINER
        _PG_CONTAINER = PostgresContainer("postgres:16-alpine")
        _PG_CONTAINER.start()
        return _PG_CONTAINER.get_connection_url().replace("postgresql://", "postgresql+psycopg2://")
    except Exception:
        return None


_PG_CONTAINER = None


@pytest.fixture(scope="module")
def db_url() -> str:
    url = _resolve_database_url()
    if url is None:
        pytest.skip("No reachable Postgres (set DATABASE_URL or run "
                    "compose `db` service); skipping parity integration test")
    yield url
    # Best-effort container teardown.
    if _PG_CONTAINER is not None:
        try:
            _PG_CONTAINER.stop()
        except Exception:
            pass


@pytest.fixture(scope="module")
def app_and_repo(db_url, tmp_path_factory):
    """Configure app + repo + ephemeral DATA_DIR and apply migrations."""
    os.environ["DATABASE_URL"] = db_url
    os.environ["DUAL_WRITE_ENABLED"] = "true"
    os.environ["READ_FROM_DB"] = "true"
    os.environ["WRITE_JSON_STATE"] = "true"  # belt-and-suspenders for parity

    data_dir = tmp_path_factory.mktemp("docdiff_data")
    os.environ["DATA_DIR"] = str(data_dir)

    # Re-import settings + db package so they pick up the new DATABASE_URL.
    import importlib

    import docdiffops.settings as settings  # noqa: F401
    importlib.reload(settings)
    from docdiffops import db as db_pkg
    importlib.reload(db_pkg)
    from docdiffops.db import models as db_models
    importlib.reload(db_models)
    from docdiffops.db import repository as repo_module
    importlib.reload(repo_module)

    db_models.Base.metadata.create_all(db_pkg.engine)

    # Reload state + main so they pick up the reloaded DB modules.
    import docdiffops.state as state_module
    importlib.reload(state_module)
    import docdiffops.pipeline as pipeline_module
    importlib.reload(pipeline_module)
    import docdiffops.main as main_module
    importlib.reload(main_module)

    from fastapi.testclient import TestClient

    client = TestClient(main_module.app)
    repo = repo_module.BatchRepository()
    yield client, repo, state_module, data_dir

    # Cleanup tables (best-effort).
    try:
        db_models.Base.metadata.drop_all(db_pkg.engine)
    except Exception:
        pass


def _fixture_paths() -> list[Path]:
    """Three fixtures from /home/dev/diff/input matching PR-1.1 baseline."""
    repo_root = Path(__file__).resolve().parents[3]
    candidates = [
        repo_root / "input" / "rasporjazenie_30r_2024.pdf",
        repo_root / "input" / "concept_2026_2030_kremlin.html",
        repo_root / "input" / "sample_neuron_comparison_brief.xlsx",
    ]
    missing = [str(p) for p in candidates if not p.exists()]
    if missing:
        pytest.skip(f"Missing fixtures: {missing}")
    return candidates


def test_dual_write_parity_full_pipeline(app_and_repo):
    """Run a 3-fixture batch through the API and assert JSON↔DB parity."""
    client, repo, state_module, _ = app_and_repo

    # 1. Create batch.
    r = client.post("/batches", json={"title": "parity test"})
    assert r.status_code == 200, r.text
    batch_id = r.json()["batch_id"]

    # 2. Upload three fixtures.
    fixtures = _fixture_paths()
    files = []
    handles = []
    try:
        for p in fixtures:
            h = p.open("rb")
            handles.append(h)
            files.append(("files", (p.name, h, "application/octet-stream")))
        r = client.post(f"/batches/{batch_id}/documents", files=files)
        assert r.status_code == 200, r.text
        assert len(r.json()["added"]) == 3
    finally:
        for h in handles:
            h.close()

    # 3. Run sync.
    r = client.post(f"/batches/{batch_id}/run", params={"profile": "fast", "sync": "true"})
    assert r.status_code == 200, r.text
    metrics = r.json().get("metrics") or {}
    assert metrics.get("documents") == 3
    assert metrics.get("pairs") == 3  # C(3,2)

    # 4. Compare JSON-only state vs DB-built state.
    json_state = state_module._load_json_only(batch_id)
    db_state = repo.to_state_dict(batch_id)
    assert db_state is not None, "DB has no row for batch — dual-write regressed"

    # documents: same set of doc_ids and sha256s.
    j_docs = {d["doc_id"]: d for d in json_state.get("documents", [])}
    d_docs = {d["doc_id"]: d for d in db_state.get("documents", [])}
    assert set(j_docs) == set(d_docs), "document ids diverged between JSON and DB"
    for did in j_docs:
        assert j_docs[did]["sha256"] == d_docs[did]["sha256"]
        assert j_docs[did].get("source_rank") == d_docs[did]["source_rank"]

    # pair_runs: every JSON pair has a matching pair_run row with status.
    j_pair_ids = {p["pair_id"] for p in json_state.get("pairs", [])}
    d_pair_runs = {pr["pair_id"]: pr for pr in db_state.get("pair_runs", [])}
    assert j_pair_ids == set(d_pair_runs), "pair_ids diverged"
    for pid, pr in d_pair_runs.items():
        assert pr["status"] in {"finished", "running", "pending"}, pr

    # diff_events: count parity between JSON jsonl files and DB rows.
    base = state_module.batch_dir(batch_id)
    json_event_count = 0
    for pid in j_pair_ids:
        jsonl = base / "pairs" / pid / "diff_events.jsonl"
        if jsonl.exists():
            json_event_count += sum(1 for line in jsonl.read_text().splitlines() if line.strip())
    db_event_count = len(db_state.get("diff_events", []))
    assert json_event_count == db_event_count, (
        f"diff_events count mismatch: json={json_event_count} db={db_event_count}"
    )

    # Sanity: at least one event of each shape we promise downstream consumers.
    statuses = {e["status"] for e in db_state["diff_events"]}
    severities = {e["severity"] for e in db_state["diff_events"]}
    assert statuses, "no diff events at all — pipeline regressed"
    assert severities <= {"low", "medium", "high"}
    assert all(e["status"] in {"same", "partial", "modified", "added", "deleted",
                               "contradicts", "manual_review", "not_found"}
               for e in db_state["diff_events"])
