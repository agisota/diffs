"""baseline schema (batches, documents, versions, pairs, events, reviews, artifacts)

Revision ID: b852f3e2882b
Revises: 
Create Date: 2026-05-08 22:21:08.907755

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b852f3e2882b'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the Sprint-1 baseline schema (PR-1.1)."""
    op.create_table('batches',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=512), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('artifacts',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('batch_id', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=64), nullable=False),
    sa.Column('path', sa.String(length=1024), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=True),
    sa.Column('size_bytes', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_artifacts_batch_id', 'artifacts', ['batch_id'], unique=False)
    op.create_table('documents',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('batch_id', sa.String(length=64), nullable=False),
    sa.Column('filename', sa.String(length=512), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('extension', sa.String(length=16), nullable=True),
    sa.Column('source_rank', sa.Integer(), nullable=False),
    sa.Column('doc_type', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('batch_id', 'sha256', name='uq_documents_batch_sha')
    )
    op.create_index('ix_documents_batch_id', 'documents', ['batch_id'], unique=False)
    op.create_table('document_versions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('document_id', sa.String(length=64), nullable=False),
    sa.Column('batch_id', sa.String(length=64), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('normalized_path', sa.String(length=1024), nullable=True),
    sa.Column('extracted_path', sa.String(length=1024), nullable=True),
    sa.Column('extractor_version', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_document_versions_batch_id', 'document_versions', ['batch_id'], unique=False)
    op.create_index('ix_document_versions_document_id', 'document_versions', ['document_id'], unique=False)
    op.create_table('pair_runs',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('batch_id', sa.String(length=64), nullable=False),
    sa.Column('lhs_document_version_id', sa.String(length=64), nullable=False),
    sa.Column('rhs_document_version_id', sa.String(length=64), nullable=False),
    sa.Column('comparator_version', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lhs_document_version_id'], ['document_versions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['rhs_document_version_id'], ['document_versions.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_pair_runs_batch_id', 'pair_runs', ['batch_id'], unique=False)
    op.create_table('diff_events',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('pair_run_id', sa.String(length=64), nullable=False),
    sa.Column('comparison_type', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('severity', sa.String(length=16), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('lhs_doc_id', sa.String(length=64), nullable=True),
    sa.Column('lhs_page', sa.Integer(), nullable=True),
    sa.Column('lhs_block_id', sa.String(length=64), nullable=True),
    sa.Column('lhs_bbox', sa.JSON(), nullable=True),
    sa.Column('lhs_quote', sa.Text(), nullable=True),
    sa.Column('rhs_doc_id', sa.String(length=64), nullable=True),
    sa.Column('rhs_page', sa.Integer(), nullable=True),
    sa.Column('rhs_block_id', sa.String(length=64), nullable=True),
    sa.Column('rhs_bbox', sa.JSON(), nullable=True),
    sa.Column('rhs_quote', sa.Text(), nullable=True),
    sa.Column('explanation_short', sa.Text(), nullable=True),
    sa.Column('review_required', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['pair_run_id'], ['pair_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_diff_events_pair_run_id', 'diff_events', ['pair_run_id'], unique=False)
    op.create_table('review_decisions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('event_id', sa.String(length=64), nullable=False),
    sa.Column('reviewer_name', sa.String(length=128), nullable=False),
    sa.Column('decision', sa.String(length=32), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['event_id'], ['diff_events.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_review_decisions_event_id', 'review_decisions', ['event_id'], unique=False)


def downgrade() -> None:
    """Drop the Sprint-1 baseline schema (reverse order, FK-safe)."""
    op.drop_index('ix_review_decisions_event_id', table_name='review_decisions')
    op.drop_table('review_decisions')
    op.drop_index('ix_diff_events_pair_run_id', table_name='diff_events')
    op.drop_table('diff_events')
    op.drop_index('ix_pair_runs_batch_id', table_name='pair_runs')
    op.drop_table('pair_runs')
    op.drop_index('ix_document_versions_document_id', table_name='document_versions')
    op.drop_index('ix_document_versions_batch_id', table_name='document_versions')
    op.drop_table('document_versions')
    op.drop_index('ix_documents_batch_id', table_name='documents')
    op.drop_table('documents')
    op.drop_index('ix_artifacts_batch_id', table_name='artifacts')
    op.drop_table('artifacts')
    op.drop_table('batches')
