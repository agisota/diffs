"""add audit_log table (PR-4.6)

Revision ID: a7d3e91b4c20
Revises: 9c7a4f1e0d51
Create Date: 2026-05-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a7d3e91b4c20"
down_revision: Union[str, Sequence[str], None] = "9c7a4f1e0d51"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "batch_id",
            sa.String(64),
            sa.ForeignKey("batches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor", sa.String(128), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_kind", sa.String(64), nullable=True),
        sa.Column("target_id", sa.String(128), nullable=True),
        sa.Column("payload", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_batch_id", "audit_log", ["batch_id"])
    op.create_index("ix_audit_action", "audit_log", ["action"])
    op.create_index("ix_audit_created_at", "audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_created_at", table_name="audit_log")
    op.drop_index("ix_audit_action", table_name="audit_log")
    op.drop_index("ix_audit_batch_id", table_name="audit_log")
    op.drop_table("audit_log")
