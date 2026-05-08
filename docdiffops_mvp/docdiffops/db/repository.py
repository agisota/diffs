"""Repository facade over the SQLAlchemy session.

PR-1.2 introduces this layer as the *write* path that runs alongside the
existing JSON state writes in ``docdiffops/state.py``. JSON remains the
read source of truth; PR-1.3 will flip reads to the repository.

Design choices (per PLAN §5 PR-1.2 and §3 ADR-1):

- Methods mirror ``state.py`` semantics so the dual-write call sites stay
  symmetric (one JSON write, one repository call).
- Each method opens its own short-lived session via ``get_session()``.
  Callers must *not* manage sessions; this is intentional so the dual
  writes from ``state.py`` cannot leak transaction state across calls.
- All "add" methods are idempotent on retry: the dual-write path may
  invoke a method twice (e.g. partial JSON write succeeds, DB write
  hiccups, retry fires). Returning the existing row instead of raising
  ``IntegrityError`` keeps the pipeline crash-free.
- Idempotency keys come from the schema's natural uniqueness:
  - ``Batch.id`` is the primary key.
  - ``Document``: PK ``id``, plus ``UNIQUE(batch_id, sha256)``.
  - ``DocumentVersion``: PK ``id``.
  - ``PairRun``: PK ``id``.
  - ``DiffEvent``: PK ``id`` (the brief's ``event_id``).
  - ``Artifact``: ``(batch_id, kind, path)`` triple matches state.py's
    dedupe rule in ``add_artifact``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from . import get_session
from .models import (
    Artifact,
    Batch,
    DiffEvent,
    Document,
    DocumentVersion,
    PairRun,
)


class BatchRepository:
    """Thin facade over the schema; one method per state.py call site."""

    # ------------------------------------------------------------------
    # Batch
    # ------------------------------------------------------------------

    def create_batch(self, batch_id: str, title: str | None = None) -> Batch:
        """Insert a Batch or return the existing row on retry."""
        with get_session() as session:
            existing = session.get(Batch, batch_id)
            if existing is not None:
                return existing
            batch = Batch(id=batch_id, title=title, status="created")
            session.add(batch)
            try:
                session.flush()
            except IntegrityError:
                # Lost race; re-fetch.
                session.rollback()
                return session.get(Batch, batch_id)  # type: ignore[return-value]
            session.refresh(batch)
            return batch

    def get_batch(self, batch_id: str) -> Optional[Batch]:
        with get_session() as session:
            return session.get(Batch, batch_id)

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    def add_document(
        self,
        batch_id: str,
        doc_id: str,
        filename: str,
        sha256: str,
        extension: str | None,
        source_rank: int,
        doc_type: str | None,
    ) -> Document:
        """Insert a Document.

        Idempotency: if a row with the same ``(batch_id, sha256)`` already
        exists, return it instead of raising ``IntegrityError``. Same if
        ``doc_id`` already exists. The brief uses sha256 as the natural
        de-dupe key for re-uploads, so we honor both PK and UNIQUE.
        """
        with get_session() as session:
            existing = session.get(Document, doc_id)
            if existing is not None:
                return existing
            existing_by_sha = session.scalar(
                select(Document).where(
                    Document.batch_id == batch_id,
                    Document.sha256 == sha256,
                )
            )
            if existing_by_sha is not None:
                return existing_by_sha
            doc = Document(
                id=doc_id,
                batch_id=batch_id,
                filename=filename,
                sha256=sha256,
                extension=extension,
                source_rank=source_rank,
                doc_type=doc_type,
                status="uploaded",
            )
            session.add(doc)
            try:
                session.flush()
            except IntegrityError:
                # Distinguish a duplicate-key race (idempotent retry) from
                # a real constraint violation (FK to non-existent batch).
                session.rollback()
                with get_session() as s2:
                    again = s2.get(Document, doc_id)
                    if again is not None:
                        return again
                    again_by_sha = s2.scalar(
                        select(Document).where(
                            Document.batch_id == batch_id,
                            Document.sha256 == sha256,
                        )
                    )
                    if again_by_sha is not None:
                        return again_by_sha
                # Genuine integrity failure (e.g. FK to missing batch);
                # bubble up so callers see real errors.
                raise
            session.refresh(doc)
            return doc

    def list_batch_documents(self, batch_id: str) -> list[Document]:
        with get_session() as session:
            rows = session.scalars(
                select(Document).where(Document.batch_id == batch_id)
            ).all()
            for r in rows:
                session.expunge(r)
            return list(rows)

    # ------------------------------------------------------------------
    # Document versions
    # ------------------------------------------------------------------

    def add_document_version(
        self,
        document_id: str,
        version: int,
        sha256: str,
        normalized_path: str | None,
        extracted_path: str | None,
        extractor_version: str,
    ) -> DocumentVersion:
        """Insert a DocumentVersion. Returns the existing row on retry."""
        # The version PK is composed of (document_id, version, extractor_version).
        # Caller mints a stable id so retries hit the PK directly.
        with get_session() as session:
            doc = session.get(Document, document_id)
            if doc is None:
                raise ValueError(f"document_id {document_id} not found")
            # Check if a version with the same (document_id, version,
            # extractor_version) already exists; if so, return it.
            existing = session.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.version == version,
                    DocumentVersion.extractor_version == extractor_version,
                )
            )
            if existing is not None:
                return existing
            dv_id = _document_version_id(document_id, version, extractor_version)
            existing_by_id = session.get(DocumentVersion, dv_id)
            if existing_by_id is not None:
                return existing_by_id
            dv = DocumentVersion(
                id=dv_id,
                document_id=document_id,
                batch_id=doc.batch_id,
                version=version,
                sha256=sha256,
                normalized_path=normalized_path,
                extracted_path=extracted_path,
                extractor_version=extractor_version,
            )
            session.add(dv)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                with get_session() as s2:
                    again = s2.get(DocumentVersion, dv_id)
                    if again is not None:
                        return again
                raise
            session.refresh(dv)
            return dv

    # ------------------------------------------------------------------
    # Pair runs
    # ------------------------------------------------------------------

    def add_pair_run(
        self,
        batch_id: str,
        pair_id: str,
        lhs_doc_version_id: str,
        rhs_doc_version_id: str,
        comparator_version: str,
    ) -> PairRun:
        with get_session() as session:
            existing = session.get(PairRun, pair_id)
            if existing is not None:
                return existing
            pr = PairRun(
                id=pair_id,
                batch_id=batch_id,
                lhs_document_version_id=lhs_doc_version_id,
                rhs_document_version_id=rhs_doc_version_id,
                comparator_version=comparator_version,
                status="pending",
            )
            session.add(pr)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                with get_session() as s2:
                    again = s2.get(PairRun, pair_id)
                    if again is not None:
                        return again
                raise
            session.refresh(pr)
            return pr

    def update_pair_run_status(
        self,
        pair_id: str,
        status: str,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        with get_session() as session:
            pr = session.get(PairRun, pair_id)
            if pr is None:
                return
            pr.status = status
            if started_at is not None:
                pr.started_at = started_at
            if finished_at is not None:
                pr.finished_at = finished_at

    # ------------------------------------------------------------------
    # Diff events
    # ------------------------------------------------------------------

    def add_diff_event(
        self,
        event_id: str,
        pair_run_id: str,
        comparison_type: str,
        status: str,
        severity: str,
        confidence: float | None,
        lhs_doc_id: str | None = None,
        lhs_page: int | None = None,
        lhs_block_id: str | None = None,
        lhs_bbox: dict | None = None,
        lhs_quote: str | None = None,
        rhs_doc_id: str | None = None,
        rhs_page: int | None = None,
        rhs_block_id: str | None = None,
        rhs_bbox: dict | None = None,
        rhs_quote: str | None = None,
        explanation_short: str | None = None,
        review_required: bool = False,
    ) -> DiffEvent:
        """Insert a DiffEvent. Idempotent on event_id collision."""
        with get_session() as session:
            existing = session.get(DiffEvent, event_id)
            if existing is not None:
                return existing
            ev = DiffEvent(
                id=event_id,
                pair_run_id=pair_run_id,
                comparison_type=comparison_type,
                status=status,
                severity=severity,
                confidence=confidence,
                lhs_doc_id=lhs_doc_id,
                lhs_page=lhs_page,
                lhs_block_id=lhs_block_id,
                lhs_bbox=lhs_bbox,
                lhs_quote=lhs_quote,
                rhs_doc_id=rhs_doc_id,
                rhs_page=rhs_page,
                rhs_block_id=rhs_block_id,
                rhs_bbox=rhs_bbox,
                rhs_quote=rhs_quote,
                explanation_short=explanation_short,
                review_required=review_required,
            )
            session.add(ev)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                with get_session() as s2:
                    again = s2.get(DiffEvent, event_id)
                    if again is not None:
                        return again
                raise
            session.refresh(ev)
            return ev

    def list_batch_events(self, batch_id: str) -> list[DiffEvent]:
        with get_session() as session:
            rows = session.scalars(
                select(DiffEvent)
                .join(PairRun, PairRun.id == DiffEvent.pair_run_id)
                .where(PairRun.batch_id == batch_id)
            ).all()
            for r in rows:
                session.expunge(r)
            return list(rows)

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------

    def add_artifact(
        self,
        batch_id: str,
        kind: str,
        path: str,
        sha256: str | None = None,
        size_bytes: int | None = None,
    ) -> Artifact:
        """Insert an Artifact. Dedup key: ``(batch_id, kind, path)``.

        Mirrors state.py's ``add_artifact`` dedupe rule. The ``id`` is a
        deterministic hash of the dedup tuple so retries idempotently
        resolve to the same row.
        """
        artifact_id = _artifact_id(batch_id, kind, path)
        with get_session() as session:
            existing = session.get(Artifact, artifact_id)
            if existing is not None:
                return existing
            art = Artifact(
                id=artifact_id,
                batch_id=batch_id,
                kind=kind,
                path=path,
                sha256=sha256,
                size_bytes=size_bytes,
            )
            session.add(art)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                with get_session() as s2:
                    again = s2.get(Artifact, artifact_id)
                    if again is not None:
                        return again
                raise
            session.refresh(art)
            return art


# ---------------------------------------------------------------------------
# Stable id helpers (kept private to the module).
# ---------------------------------------------------------------------------


def _document_version_id(document_id: str, version: int, extractor_version: str) -> str:
    from ..utils import stable_id

    return "dv_" + stable_id(document_id, str(version), extractor_version, n=20)


def _artifact_id(batch_id: str, kind: str, path: str) -> str:
    from ..utils import stable_id

    return "art_" + stable_id(batch_id, kind, path, n=20)


__all__ = ["BatchRepository"]
