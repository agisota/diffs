"""Unit tests for ``docdiffops.db.repository.BatchRepository`` (PR-1.2).

Tests run against the same SQLite-by-default fixture pattern PR-1.1
``test_models.py`` established. The repository imports ``get_session``
from ``docdiffops.db.__init__``, which binds to the engine built from
``DATABASE_URL``. Tests rebind both the engine and the ``SessionLocal``
factory so every test sees an isolated database.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from docdiffops.db import models as db_models
from docdiffops.db.models import Base


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@pytest.fixture()
def repo(monkeypatch):
    """Build an isolated engine, rebind ``get_session``, return a repo."""
    from docdiffops import db as db_pkg
    from docdiffops.db import repository as repo_module

    url = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")
    eng = create_engine(url, future=True)

    if eng.dialect.name == "sqlite":
        @event.listens_for(eng, "connect")
        def _enable_fk(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    Base.metadata.create_all(eng)
    SessionLocal = sessionmaker(bind=eng, autoflush=False, future=True,
                                 expire_on_commit=False)

    # Rebind the module-level engine + session factory used by repository.
    monkeypatch.setattr(db_pkg, "engine", eng)
    monkeypatch.setattr(db_pkg, "SessionLocal", SessionLocal)
    # Repository imports ``get_session`` directly from db_pkg, but it does
    # so via ``from . import get_session`` so we replace the function used
    # by the contextmanager's bound SessionLocal. Easiest path: monkeypatch
    # the get_session reference inside the repository module.
    from contextlib import contextmanager

    @contextmanager
    def _local_session():
        s = SessionLocal()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    monkeypatch.setattr(repo_module, "get_session", _local_session)

    yield repo_module.BatchRepository()

    Base.metadata.drop_all(eng)
    eng.dispose()


# ---------------------------------------------------------------------------
# create_batch
# ---------------------------------------------------------------------------


def test_create_batch_inserts_and_returns_row(repo) -> None:
    bid = _new_id("bat")
    b = repo.create_batch(bid, title="hello")
    assert b.id == bid
    assert b.title == "hello"


def test_create_batch_idempotent_on_retry(repo) -> None:
    bid = _new_id("bat")
    b1 = repo.create_batch(bid, title="first")
    b2 = repo.create_batch(bid, title="second")  # retry
    assert b1.id == b2.id
    # First write wins; we do not overwrite title on retry.
    assert b2.title == "first"


def test_get_batch_returns_none_for_missing(repo) -> None:
    assert repo.get_batch("bat_missing") is None


# ---------------------------------------------------------------------------
# add_document
# ---------------------------------------------------------------------------


def test_add_document_idempotent_by_doc_id(repo) -> None:
    bid = _new_id("bat")
    repo.create_batch(bid, title="b")
    did = _new_id("doc")
    sha = "a" * 64
    d1 = repo.add_document(bid, did, "a.pdf", sha, ".pdf", 2, "LEGAL_NPA")
    d2 = repo.add_document(bid, did, "a.pdf", sha, ".pdf", 2, "LEGAL_NPA")
    assert d1.id == d2.id


def test_add_document_idempotent_by_batch_sha(repo) -> None:
    """Re-adding with a different doc_id but the same (batch_id, sha256)
    must return the existing row, not raise IntegrityError."""
    bid = _new_id("bat")
    repo.create_batch(bid, title="b")
    sha = "b" * 64
    d1 = repo.add_document(bid, _new_id("doc"), "a.pdf", sha, ".pdf", 3, None)
    d2 = repo.add_document(bid, _new_id("doc"), "a.pdf", sha, ".pdf", 3, None)
    assert d1.id == d2.id  # second call returned the first row


def test_add_document_fk_violation_raises(repo) -> None:
    """A document referencing a non-existent batch must fail with an
    IntegrityError on FK rather than silently succeeding."""
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        repo.add_document("bat_nope", _new_id("doc"), "x.pdf",
                          "c" * 64, ".pdf", 3, None)


def test_list_batch_documents_returns_only_batch_rows(repo) -> None:
    bid_a, bid_b = _new_id("bat"), _new_id("bat")
    repo.create_batch(bid_a)
    repo.create_batch(bid_b)
    repo.add_document(bid_a, _new_id("doc"), "a.pdf", "1" * 64, ".pdf", 3, None)
    repo.add_document(bid_a, _new_id("doc"), "b.pdf", "2" * 64, ".pdf", 3, None)
    repo.add_document(bid_b, _new_id("doc"), "c.pdf", "3" * 64, ".pdf", 3, None)
    docs_a = repo.list_batch_documents(bid_a)
    docs_b = repo.list_batch_documents(bid_b)
    assert len(docs_a) == 2
    assert len(docs_b) == 1


# ---------------------------------------------------------------------------
# add_document_version + add_pair_run + update_pair_run_status
# ---------------------------------------------------------------------------


def test_add_document_version_idempotent(repo) -> None:
    bid = _new_id("bat")
    repo.create_batch(bid)
    did = _new_id("doc")
    repo.add_document(bid, did, "a.pdf", "a" * 64, ".pdf", 3, None)
    dv1 = repo.add_document_version(did, 1, "a" * 64, "n.pdf", "e.json", "2.B.0")
    dv2 = repo.add_document_version(did, 1, "a" * 64, "n.pdf", "e.json", "2.B.0")
    assert dv1.id == dv2.id


def test_add_document_version_unknown_doc_raises(repo) -> None:
    with pytest.raises(ValueError):
        repo.add_document_version("doc_nope", 1, "a" * 64, None, None, "2.B.0")


def test_add_pair_run_and_update_status(repo) -> None:
    bid = _new_id("bat")
    repo.create_batch(bid)
    did_a, did_b = _new_id("doc"), _new_id("doc")
    repo.add_document(bid, did_a, "a.pdf", "a" * 64, ".pdf", 3, None)
    repo.add_document(bid, did_b, "b.pdf", "b" * 64, ".pdf", 3, None)
    dv_a = repo.add_document_version(did_a, 1, "a" * 64, None, None, "2.B.0")
    dv_b = repo.add_document_version(did_b, 1, "b" * 64, None, None, "2.B.0")
    pid = _new_id("pair")
    pr = repo.add_pair_run(bid, pid, dv_a.id, dv_b.id, "1.0.0")
    assert pr.id == pid
    assert pr.status == "pending"
    # Idempotent retry.
    pr2 = repo.add_pair_run(bid, pid, dv_a.id, dv_b.id, "1.0.0")
    assert pr2.id == pid
    # Update status.
    repo.update_pair_run_status(pid, "running")
    repo.update_pair_run_status(pid, "finished")
    # Updating a missing pair_run is a no-op (no exception).
    repo.update_pair_run_status("pair_nope", "finished")


# ---------------------------------------------------------------------------
# add_diff_event + list_batch_events
# ---------------------------------------------------------------------------


def test_add_diff_event_idempotent(repo) -> None:
    bid = _new_id("bat")
    repo.create_batch(bid)
    did_a, did_b = _new_id("doc"), _new_id("doc")
    repo.add_document(bid, did_a, "a.pdf", "a" * 64, ".pdf", 3, None)
    repo.add_document(bid, did_b, "b.pdf", "b" * 64, ".pdf", 3, None)
    dv_a = repo.add_document_version(did_a, 1, "a" * 64, None, None, "2.B.0")
    dv_b = repo.add_document_version(did_b, 1, "b" * 64, None, None, "2.B.0")
    pid = _new_id("pair")
    repo.add_pair_run(bid, pid, dv_a.id, dv_b.id, "1.0.0")
    eid = _new_id("evt")
    e1 = repo.add_diff_event(
        eid, pid, "block_semantic_diff", "partial", "medium", 0.81,
        lhs_doc_id=did_a, rhs_doc_id=did_b,
        explanation_short="paraphrase", review_required=True,
    )
    # Retry must NOT raise.
    e2 = repo.add_diff_event(
        eid, pid, "block_semantic_diff", "partial", "medium", 0.81,
        lhs_doc_id=did_a, rhs_doc_id=did_b,
        explanation_short="paraphrase", review_required=True,
    )
    assert e1.id == e2.id
    events = repo.list_batch_events(bid)
    assert len(events) == 1
    assert events[0].id == eid


def test_add_diff_event_fk_violation_raises(repo) -> None:
    """An event with a non-existent pair_run_id must fail FK."""
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        repo.add_diff_event(
            _new_id("evt"), "pair_nope", "block_semantic_diff",
            "partial", "medium", 0.5,
        )


def test_list_batch_events_scopes_to_batch(repo) -> None:
    bid_a, bid_b = _new_id("bat"), _new_id("bat")
    for bid in (bid_a, bid_b):
        repo.create_batch(bid)
        did_a, did_b = _new_id("doc"), _new_id("doc")
        repo.add_document(bid, did_a, "a.pdf", _new_id("h"), ".pdf", 3, None)
        repo.add_document(bid, did_b, "b.pdf", _new_id("h"), ".pdf", 3, None)
        dv_a = repo.add_document_version(did_a, 1, "a" * 64, None, None, f"e_{bid}")
        dv_b = repo.add_document_version(did_b, 1, "b" * 64, None, None, f"e_{bid}")
        pid = _new_id("pair")
        repo.add_pair_run(bid, pid, dv_a.id, dv_b.id, "1.0.0")
        repo.add_diff_event(_new_id("evt"), pid, "block_semantic_diff",
                            "same", "low", 0.95)
    assert len(repo.list_batch_events(bid_a)) == 1
    assert len(repo.list_batch_events(bid_b)) == 1


# ---------------------------------------------------------------------------
# add_artifact
# ---------------------------------------------------------------------------


def test_add_artifact_idempotent_on_dedup_tuple(repo) -> None:
    bid = _new_id("bat")
    repo.create_batch(bid)
    a1 = repo.add_artifact(bid, "evidence_xlsx",
                           "reports/evidence_matrix.xlsx",
                           sha256="c" * 64, size_bytes=12345)
    a2 = repo.add_artifact(bid, "evidence_xlsx",
                           "reports/evidence_matrix.xlsx",
                           sha256="c" * 64, size_bytes=12345)
    assert a1.id == a2.id


def test_add_artifact_distinct_for_different_path(repo) -> None:
    bid = _new_id("bat")
    repo.create_batch(bid)
    a = repo.add_artifact(bid, "redgreen_pdf", "pairs/p1/rg.pdf")
    b = repo.add_artifact(bid, "redgreen_pdf", "pairs/p2/rg.pdf")
    assert a.id != b.id
