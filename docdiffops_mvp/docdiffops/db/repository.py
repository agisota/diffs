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

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from . import get_session
from .models import (
    Artifact,
    Batch,
    DiffEvent,
    Document,
    DocumentVersion,
    PairRun,
    SourceRegistry,
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
        source_url: str | None = None,
    ) -> Document:
        """Insert a Document.

        Idempotency: if a row with the same ``(batch_id, sha256)`` already
        exists, return it instead of raising ``IntegrityError``. Same if
        ``doc_id`` already exists. The brief uses sha256 as the natural
        de-dupe key for re-uploads, so we honor both PK and UNIQUE.

        ``source_url`` (PR-1.5) is the optional provenance URL recorded at
        upload time. ``None`` for locally-uploaded files.
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
                source_url=source_url,
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
    # Read path (PR-1.3)
    # ------------------------------------------------------------------

    def to_state_dict(self, batch_id: str) -> dict | None:
        """Build a state.py-shaped dict for ``batch_id`` from DB rows.

        The output shape mirrors what ``state.load_state`` returned in
        PR-1.2, so the FastAPI endpoints that consume the dict don't see
        any change. The DB does not track three JSON-only fields
        (``config``, ``runs``, ``metrics``); they default to empty
        containers when read from DB. Callers that need those fields
        verbatim should fall back to the JSON file.

        Returns ``None`` when the batch row does not exist in the DB —
        callers (state.load_state) treat ``None`` as "fall back to JSON".
        """
        with get_session() as session:
            batch = session.get(Batch, batch_id)
            if batch is None:
                return None

            documents = list(
                session.scalars(
                    select(Document).where(Document.batch_id == batch_id)
                ).all()
            )
            pair_rows = list(
                session.scalars(
                    select(PairRun).where(PairRun.batch_id == batch_id)
                ).all()
            )
            event_rows = list(
                session.scalars(
                    select(DiffEvent)
                    .join(PairRun, PairRun.id == DiffEvent.pair_run_id)
                    .where(PairRun.batch_id == batch_id)
                ).all()
            )
            artifact_rows = list(
                session.scalars(
                    select(Artifact).where(Artifact.batch_id == batch_id)
                ).all()
            )

            # We need lhs/rhs doc_id for each pair_run, which the schema
            # only has via document_versions. Resolve once.
            dv_ids: set[str] = set()
            for pr in pair_rows:
                dv_ids.add(pr.lhs_document_version_id)
                dv_ids.add(pr.rhs_document_version_id)
            dv_to_doc: dict[str, str] = {}
            if dv_ids:
                dv_rows = session.scalars(
                    select(DocumentVersion).where(DocumentVersion.id.in_(dv_ids))
                ).all()
                dv_to_doc = {dv.id: dv.document_id for dv in dv_rows}

            doc_dicts = [_document_to_dict(d) for d in documents]
            pair_dicts = [_pair_run_to_dict(pr, dv_to_doc) for pr in pair_rows]
            event_dicts = [_event_to_dict(e) for e in event_rows]
            artifact_dicts = [_artifact_to_dict(a) for a in artifact_rows]

            return {
                "batch_id": batch.id,
                "title": batch.title or batch.id,
                "status": batch.status,
                "created_at": _fmt_dt(batch.created_at),
                "updated_at": _fmt_dt(batch.updated_at),
                # JSON-only fields the DB does not track; preserve shape.
                "config": {},
                "runs": [],
                "metrics": {},
                # Core lists.
                "documents": doc_dicts,
                # ``pairs`` mirrors the JSON shape the existing renderers
                # and FastAPI clients consume; ``pair_runs`` is the richer
                # DB-backed view added in PR-1.3 with status timestamps.
                "pairs": [
                    {
                        "pair_id": p["pair_id"],
                        "lhs_doc_id": p["lhs_doc_id"],
                        "rhs_doc_id": p["rhs_doc_id"],
                    }
                    for p in pair_dicts
                ],
                "pair_runs": pair_dicts,
                "diff_events": event_dicts,
                "artifacts": artifact_dicts,
            }

    def list_all_batches(self) -> list[dict]:
        """Return a summary list of all batches in the DB.

        Mirrors ``state.list_batches`` semantics: one dict per batch
        with ``batch_id``, ``title``, ``created_at``, ``updated_at``,
        ``status`` plus aggregate counts for documents/pair_runs/events.
        """
        with get_session() as session:
            batches = session.scalars(select(Batch)).all()
            out: list[dict] = []
            for b in batches:
                doc_count = session.scalar(
                    select(func.count(Document.id)).where(Document.batch_id == b.id)
                ) or 0
                pair_count = session.scalar(
                    select(func.count(PairRun.id)).where(PairRun.batch_id == b.id)
                ) or 0
                event_count = session.scalar(
                    select(func.count(DiffEvent.id))
                    .join(PairRun, PairRun.id == DiffEvent.pair_run_id)
                    .where(PairRun.batch_id == b.id)
                ) or 0
                out.append({
                    "batch_id": b.id,
                    "title": b.title or b.id,
                    "status": b.status,
                    "created_at": _fmt_dt(b.created_at),
                    "updated_at": _fmt_dt(b.updated_at),
                    "documents_count": int(doc_count),
                    "pair_runs_count": int(pair_count),
                    "diff_events_count": int(event_count),
                })
            return out

    # ------------------------------------------------------------------
    # Source registry (PR-1.5)
    # ------------------------------------------------------------------

    def register_source(
        self,
        url: str,
        rank: int,
        doc_type: str,
    ) -> SourceRegistry:
        """Insert or return a ``source_registry`` row keyed on URL.

        Idempotent: a second call with the same URL returns the existing
        row even if ``rank``/``doc_type`` differ. Inferred classification
        is captured at first sight; PR-3.6 may overwrite via a dedicated
        update method later.
        """
        sid = _source_registry_id(url)
        with get_session() as session:
            existing = session.scalar(
                select(SourceRegistry).where(SourceRegistry.url == url)
            )
            if existing is not None:
                session.expunge(existing)
                return existing
            row = SourceRegistry(
                id=sid,
                url=url,
                inferred_rank=rank,
                inferred_doc_type=doc_type,
            )
            session.add(row)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                with get_session() as s2:
                    again = s2.scalar(
                        select(SourceRegistry).where(SourceRegistry.url == url)
                    )
                    if again is not None:
                        s2.expunge(again)
                        return again
                raise
            session.refresh(row)
            session.expunge(row)
            return row

    def get_source(self, url: str) -> Optional[SourceRegistry]:
        """Return the registry row for ``url`` or ``None``."""
        with get_session() as session:
            row = session.scalar(
                select(SourceRegistry).where(SourceRegistry.url == url)
            )
            if row is not None:
                session.expunge(row)
            return row

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


def _source_registry_id(url: str) -> str:
    from ..utils import stable_id

    return "src_" + stable_id(url, n=20)


# ---------------------------------------------------------------------------
# Row → dict helpers for the read path (PR-1.3).
# ---------------------------------------------------------------------------


def _fmt_dt(dt: datetime | None) -> str | None:
    """Format a UTC datetime as the ISO8601 ``Z`` string state.py uses."""
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _document_to_dict(d: Document) -> dict:
    """Project a Document row into the JSON-state field shape.

    JSON-only fields not stored in the DB (``raw_path``, ``canonical_pdf``,
    ``extracted_json``, ``block_count``, ``title``) are emitted as
    ``None``/``0`` so consumers see a stable schema. The pipeline still
    populates them in the JSON when ``WRITE_JSON_STATE`` is on; callers
    that need those values should fall back to the JSON load path until
    those columns land on the schema.
    """
    return {
        "doc_id": d.id,
        "title": (d.filename.rsplit(".", 1)[0] if d.filename else d.id),
        "filename": d.filename,
        "raw_path": None,
        "sha256": d.sha256,
        "ext": d.extension,
        "source_rank": d.source_rank,
        "doc_type": d.doc_type,
        "source_url": d.source_url,
        "status": d.status,
        "canonical_pdf": None,
        "extracted_json": None,
        "block_count": 0,
    }


def _pair_run_to_dict(pr: PairRun, dv_to_doc: dict[str, str]) -> dict:
    return {
        "pair_id": pr.id,
        "lhs_doc_id": dv_to_doc.get(pr.lhs_document_version_id),
        "rhs_doc_id": dv_to_doc.get(pr.rhs_document_version_id),
        "status": pr.status,
        "comparator_version": pr.comparator_version,
        "started_at": _fmt_dt(pr.started_at),
        "finished_at": _fmt_dt(pr.finished_at),
    }


def _event_to_dict(e: DiffEvent) -> dict:
    return {
        "event_id": e.id,
        "pair_id": e.pair_run_id,
        "comparison_type": e.comparison_type,
        "status": e.status,
        "severity": e.severity,
        "confidence": e.confidence,
        "lhs": {
            "doc_id": e.lhs_doc_id,
            "page_no": e.lhs_page,
            "block_id": e.lhs_block_id,
            "bbox": e.lhs_bbox,
            "quote": e.lhs_quote,
        },
        "rhs": {
            "doc_id": e.rhs_doc_id,
            "page_no": e.rhs_page,
            "block_id": e.rhs_block_id,
            "bbox": e.rhs_bbox,
            "quote": e.rhs_quote,
        },
        "explanation_short": e.explanation_short,
        "review_required": bool(e.review_required),
    }


def _artifact_to_dict(a: Artifact) -> dict:
    return {
        "type": a.kind,
        "title": a.path.rsplit("/", 1)[-1] if a.path else a.kind,
        "path": a.path,
        "sha256": a.sha256,
        "size_bytes": a.size_bytes,
    }


__all__ = ["BatchRepository"]
