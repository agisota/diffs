"""SQLAlchemy 2.x ORM models for the Sprint-1 baseline schema.

Tables (per PLAN §3 ADR-1 and PR-1.1):
    batches, documents, document_versions, pair_runs, diff_events,
    review_decisions, artifacts.

PR-1.1 lands the schema only. The repository layer (PR-1.2) and the
read cutover (PR-1.3) come in follow-up PRs; nothing here writes from
state.py or pipeline.py yet.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)
from sqlalchemy.sql import func
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    documents: Mapped[list["Document"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )
    pair_runs: Mapped[list["PairRun"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("batches.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extension: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    doc_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # PR-1.5: provenance URL captured at upload time. Nullable for
    # locally-uploaded files where we cannot prove provenance.
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    batch: Mapped[Batch] = relationship(back_populates="documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("batch_id", "sha256", name="uq_documents_batch_sha"),
        Index("ix_documents_batch_id", "batch_id"),
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    batch_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("batches.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    extracted_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[Document] = relationship(back_populates="versions")

    __table_args__ = (
        Index("ix_document_versions_batch_id", "batch_id"),
        Index("ix_document_versions_document_id", "document_id"),
    )


class PairRun(Base):
    __tablename__ = "pair_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("batches.id", ondelete="CASCADE"), nullable=False
    )
    lhs_document_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("document_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rhs_document_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("document_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    comparator_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    batch: Mapped[Batch] = relationship(back_populates="pair_runs")
    diff_events: Mapped[list["DiffEvent"]] = relationship(
        back_populates="pair_run", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_pair_runs_batch_id", "batch_id"),)


class DiffEvent(Base):
    __tablename__ = "diff_events"

    # event_id is the primary key; the column is named `id` for consistency
    # with the rest of the schema, with a synonym attribute `event_id`.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pair_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("pair_runs.id", ondelete="CASCADE"), nullable=False
    )
    comparison_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    lhs_doc_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lhs_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lhs_block_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lhs_bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    lhs_quote: Mapped[str | None] = mapped_column(Text, nullable=True)

    rhs_doc_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rhs_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rhs_block_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rhs_bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rhs_quote: Mapped[str | None] = mapped_column(Text, nullable=True)

    explanation_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    pair_run: Mapped[PairRun] = relationship(back_populates="diff_events")
    review_decisions: Mapped[list["ReviewDecision"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_diff_events_pair_run_id", "pair_run_id"),)

    # Convenience alias: brief uses `event_id` for the same column.
    @property
    def event_id(self) -> str:
        return self.id


class ReviewDecision(Base):
    __tablename__ = "review_decisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("diff_events.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_name: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    event: Mapped[DiffEvent] = relationship(back_populates="review_decisions")

    __table_args__ = (Index("ix_review_decisions_event_id", "event_id"),)


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("batches.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    batch: Mapped[Batch] = relationship(back_populates="artifacts")

    __table_args__ = (Index("ix_artifacts_batch_id", "batch_id"),)


class AuditLog(Base):
    """PR-4.6: append-only log of state-changing API actions.

    Records who did what, when. ``actor`` is the free-text reviewer_name
    (Q1 closure: no auth, anonymous service). ``payload`` is JSON for
    flexible per-event-kind data (review decision, anchor change, etc.).
    """

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("batches.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_audit_batch_id", "batch_id"),
        Index("ix_audit_action", "action"),
        Index("ix_audit_created_at", "created_at"),
    )


class SourceRegistry(Base):
    """Registry of distinct provenance URLs encountered during uploads.

    PR-1.5 introduces this table so PR-4.4 (scheduled URL polling) has a
    place to record ``last_polled_at`` / ``last_seen_sha256`` without
    bolting more columns onto ``documents``. Multiple ``Document`` rows
    can share the same registry entry — a federal law uploaded into two
    batches is the same source, polled once.

    Idempotency key: ``url`` is unique. ``register_source`` returns the
    existing row when called twice.
    """

    __tablename__ = "source_registry"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    inferred_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    inferred_doc_type: Mapped[str] = mapped_column(String(64), nullable=False)
    last_polled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_source_registry_inferred_rank", "inferred_rank"),
    )


__all__ = [
    "Base",
    "Batch",
    "Document",
    "DocumentVersion",
    "PairRun",
    "DiffEvent",
    "ReviewDecision",
    "Artifact",
    "SourceRegistry",
]
