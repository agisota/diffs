"""Unit tests for the Sprint-1 baseline ORM models (PR-1.1).

Strategy:

- Tests run against an ephemeral SQLite database created via
  ``Base.metadata.create_all`` per test (function-scoped fixture, no
  cross-test bleed). Tests are pointed at Postgres in CI by exporting
  ``DATABASE_URL`` to a real Postgres URL — the same fixtures work,
  because we ``create_all`` and ``drop_all`` from ``Base.metadata``.
- A SQLite fallback is the documented escape hatch from PR-1.1's task
  spec: dialect differences (notably ``server_default=now()`` and
  JSON columns) are minor for these structural tests. The integrity
  tests below exercise NOT NULL, UNIQUE, and FK behavior on whichever
  dialect the test runner picks.

NOTE on FK enforcement: SQLite ignores foreign keys by default. The
fixture below issues ``PRAGMA foreign_keys = ON`` after each connect
so the FK constraint test still runs end-to-end on SQLite.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from docdiffops.db.models import (
    Artifact,
    Base,
    Batch,
    DiffEvent,
    Document,
    DocumentVersion,
    PairRun,
    ReviewDecision,
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@pytest.fixture()
def engine() -> Engine:
    url = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")
    eng = create_engine(url, future=True)

    if eng.dialect.name == "sqlite":
        @event.listens_for(eng, "connect")
        def _enable_fk(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        Base.metadata.drop_all(eng)
        eng.dispose()


@pytest.fixture()
def session(engine: Engine) -> Session:
    SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)
    sess = SessionLocal()
    try:
        yield sess
    finally:
        sess.close()


# ---------------------------------------------------------------------------
# Per-model round-trip tests
# ---------------------------------------------------------------------------


def test_batch_roundtrip(session: Session) -> None:
    bid = _new_id("bat")
    session.add(Batch(id=bid, title="t1", status="created"))
    session.commit()
    found = session.get(Batch, bid)
    assert found is not None
    assert found.title == "t1"
    assert found.status == "created"
    assert found.created_at is not None
    assert found.updated_at is not None


def test_document_roundtrip(session: Session) -> None:
    bid = _new_id("bat")
    did = _new_id("doc")
    session.add(Batch(id=bid, title="b", status="created"))
    session.add(Document(
        id=did, batch_id=bid, filename="a.pdf",
        sha256="a" * 64, extension=".pdf", source_rank=2, doc_type="LEGAL_NPA",
        status="uploaded",
    ))
    session.commit()
    doc = session.get(Document, did)
    assert doc is not None
    assert doc.batch_id == bid
    assert doc.source_rank == 2
    assert doc.doc_type == "LEGAL_NPA"


def test_document_version_roundtrip(session: Session) -> None:
    bid, did, vid = _new_id("bat"), _new_id("doc"), _new_id("dv")
    session.add(Batch(id=bid, title="b", status="created"))
    session.add(Document(id=did, batch_id=bid, filename="a.pdf",
                         sha256="a" * 64, extension=".pdf"))
    session.add(DocumentVersion(
        id=vid, document_id=did, batch_id=bid, version=1,
        sha256="a" * 64, normalized_path="n.pdf", extracted_path="e.json",
        extractor_version="2.B.docling-2.0",
    ))
    session.commit()
    dv = session.get(DocumentVersion, vid)
    assert dv is not None
    assert dv.extractor_version == "2.B.docling-2.0"


def test_pair_run_roundtrip(session: Session) -> None:
    bid = _new_id("bat")
    did_a, did_b = _new_id("doc"), _new_id("doc")
    dv_a, dv_b = _new_id("dv"), _new_id("dv")
    pid = _new_id("pair")
    session.add_all([
        Batch(id=bid, title="b", status="created"),
        Document(id=did_a, batch_id=bid, filename="a.pdf", sha256="a" * 64),
        Document(id=did_b, batch_id=bid, filename="b.pdf", sha256="b" * 64),
        DocumentVersion(id=dv_a, document_id=did_a, batch_id=bid, version=1,
                        sha256="a" * 64, extractor_version="2.B.0"),
        DocumentVersion(id=dv_b, document_id=did_b, batch_id=bid, version=1,
                        sha256="b" * 64, extractor_version="2.B.0"),
    ])
    session.commit()
    session.add(PairRun(
        id=pid, batch_id=bid,
        lhs_document_version_id=dv_a, rhs_document_version_id=dv_b,
        comparator_version="3.0.0", status="pending",
    ))
    session.commit()
    pr = session.get(PairRun, pid)
    assert pr is not None
    assert pr.lhs_document_version_id == dv_a
    assert pr.status == "pending"


def test_diff_event_roundtrip(session: Session) -> None:
    bid = _new_id("bat")
    did_a, did_b = _new_id("doc"), _new_id("doc")
    dv_a, dv_b = _new_id("dv"), _new_id("dv")
    pid, eid = _new_id("pair"), _new_id("evt")
    session.add_all([
        Batch(id=bid, title="b", status="created"),
        Document(id=did_a, batch_id=bid, filename="a.pdf", sha256="a" * 64),
        Document(id=did_b, batch_id=bid, filename="b.pdf", sha256="b" * 64),
        DocumentVersion(id=dv_a, document_id=did_a, batch_id=bid, version=1,
                        sha256="a" * 64, extractor_version="2.B.0"),
        DocumentVersion(id=dv_b, document_id=did_b, batch_id=bid, version=1,
                        sha256="b" * 64, extractor_version="2.B.0"),
    ])
    session.commit()
    session.add(PairRun(
        id=pid, batch_id=bid,
        lhs_document_version_id=dv_a, rhs_document_version_id=dv_b,
        comparator_version="3.0.0", status="finished",
    ))
    session.commit()
    session.add(DiffEvent(
        id=eid, pair_run_id=pid, comparison_type="block_semantic_diff",
        status="partial", severity="medium", confidence=0.81,
        lhs_doc_id=did_a, lhs_page=1, lhs_block_id="b1",
        lhs_bbox={"x0": 0, "y0": 0, "x1": 100, "y1": 50},
        lhs_quote="LHS quote",
        rhs_doc_id=did_b, rhs_page=2, rhs_block_id="b2",
        rhs_bbox={"x0": 5, "y0": 5, "x1": 105, "y1": 55},
        rhs_quote="RHS quote",
        explanation_short="paraphrase", review_required=True,
    ))
    session.commit()
    ev = session.get(DiffEvent, eid)
    assert ev is not None
    assert ev.event_id == eid  # synonym property
    assert ev.review_required is True
    assert ev.lhs_bbox == {"x0": 0, "y0": 0, "x1": 100, "y1": 50}


def test_review_decision_roundtrip(session: Session) -> None:
    # minimal scaffold: batch -> docs -> versions -> pair -> event -> review
    bid = _new_id("bat")
    did_a, did_b = _new_id("doc"), _new_id("doc")
    dv_a, dv_b = _new_id("dv"), _new_id("dv")
    pid, eid, rid = _new_id("pair"), _new_id("evt"), _new_id("rev")
    session.add_all([
        Batch(id=bid, status="created"),
        Document(id=did_a, batch_id=bid, filename="a.pdf", sha256="a" * 64),
        Document(id=did_b, batch_id=bid, filename="b.pdf", sha256="b" * 64),
        DocumentVersion(id=dv_a, document_id=did_a, batch_id=bid, version=1,
                        sha256="a" * 64, extractor_version="2.B.0"),
        DocumentVersion(id=dv_b, document_id=did_b, batch_id=bid, version=1,
                        sha256="b" * 64, extractor_version="2.B.0"),
    ])
    session.commit()
    session.add(PairRun(id=pid, batch_id=bid,
                        lhs_document_version_id=dv_a,
                        rhs_document_version_id=dv_b,
                        comparator_version="3.0.0", status="finished"))
    session.commit()
    session.add(DiffEvent(id=eid, pair_run_id=pid,
                          comparison_type="block_semantic_diff",
                          status="contradicts", severity="high",
                          review_required=True))
    session.commit()
    session.add(ReviewDecision(id=rid, event_id=eid, reviewer_name="alice",
                               decision="confirmed", comment="ok"))
    session.commit()
    rd = session.get(ReviewDecision, rid)
    assert rd is not None
    assert rd.reviewer_name == "alice"
    assert rd.decision == "confirmed"


def test_artifact_roundtrip(session: Session) -> None:
    bid, aid = _new_id("bat"), _new_id("art")
    session.add(Batch(id=bid, status="created"))
    session.add(Artifact(id=aid, batch_id=bid, kind="evidence_xlsx",
                         path="reports/evidence_matrix.xlsx",
                         sha256="c" * 64, size_bytes=12345))
    session.commit()
    art = session.get(Artifact, aid)
    assert art is not None
    assert art.kind == "evidence_xlsx"
    assert art.size_bytes == 12345


# ---------------------------------------------------------------------------
# Constraint tests
# ---------------------------------------------------------------------------


def test_document_sha256_not_null(session: Session) -> None:
    bid = _new_id("bat")
    session.add(Batch(id=bid, status="created"))
    session.commit()
    session.add(Document(id=_new_id("doc"), batch_id=bid,
                         filename="a.pdf", sha256=None))  # type: ignore[arg-type]
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_documents_unique_batch_sha(session: Session) -> None:
    bid = _new_id("bat")
    session.add(Batch(id=bid, status="created"))
    session.commit()
    same_hash = "d" * 64
    session.add(Document(id=_new_id("doc"), batch_id=bid,
                         filename="a.pdf", sha256=same_hash))
    session.commit()
    session.add(Document(id=_new_id("doc"), batch_id=bid,
                         filename="b.pdf", sha256=same_hash))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_diff_event_fk_pair_run_required(session: Session) -> None:
    # No matching pair_run_id exists; FK must reject.
    session.add(DiffEvent(id=_new_id("evt"), pair_run_id=_new_id("pair"),
                          comparison_type="block_semantic_diff",
                          status="partial", severity="medium",
                          review_required=False))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
