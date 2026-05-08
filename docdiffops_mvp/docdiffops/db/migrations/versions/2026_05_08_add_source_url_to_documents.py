"""add source_url to documents + create source_registry table (PR-1.5)

Revision ID: 9c7a4f1e0d51
Revises: b852f3e2882b
Create Date: 2026-05-08 23:40:00.000000

PR-1.5 wires the source registry into the schema:

* ``documents.source_url`` — nullable provenance URL captured at upload.
* ``source_registry`` — distinct URL → (inferred_rank, inferred_doc_type)
  mapping, with polling timestamps reserved for PR-4.4.

Both changes land in one cohesive migration so a fresh ``alembic upgrade
head`` rebuilds the full schema.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9c7a4f1e0d51"
down_revision: Union[str, Sequence[str], None] = "b852f3e2882b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # documents.source_url — nullable Text; backfilled lazily as old
    # uploads are re-classified.
    op.add_column(
        "documents",
        sa.Column("source_url", sa.Text(), nullable=True),
    )

    # source_registry — one row per distinct URL, owned by no batch.
    op.create_table(
        "source_registry",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("inferred_rank", sa.Integer(), nullable=False),
        sa.Column("inferred_doc_type", sa.String(length=64), nullable=False),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url", name="uq_source_registry_url"),
    )
    op.create_index(
        "ix_source_registry_inferred_rank",
        "source_registry",
        ["inferred_rank"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_source_registry_inferred_rank", table_name="source_registry")
    op.drop_table("source_registry")
    op.drop_column("documents", "source_url")
