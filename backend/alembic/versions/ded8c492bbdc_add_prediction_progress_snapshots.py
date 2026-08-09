"""add prediction progress snapshots

Revision ID: ded8c492bbdc
Revises: 001
Create Date: 2026-06-21 18:06:31.892923

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'ded8c492bbdc'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'prediction_progress',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('prediction_id', sa.String(length=50), nullable=False),
        sa.Column('match_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('snapshot_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('minute', sa.Integer(), nullable=True),
        sa.Column('period_label', sa.String(length=30), nullable=True),
        sa.Column('home_score', sa.Integer(), nullable=True),
        sa.Column('away_score', sa.Integer(), nullable=True),
        sa.Column('fulfillment_percent', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id']),
        sa.ForeignKeyConstraint(['prediction_id'], ['predictions.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.add_column(
        'predictions',
        sa.Column('live_fulfillment_percent', sa.Numeric(precision=5, scale=2), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('predictions', 'live_fulfillment_percent')
    op.drop_table('prediction_progress')
