"""Add Glicko-2 rating deviation / volatility columns.

Revision ID: c4d5e6f7a8b9
Revises: 8f3e2d1c0b4a
Create Date: 2026-09-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c4d5e6f7a8b9'
down_revision = '8f3e2d1c0b4a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'competitor_stats',
        sa.Column('rating_deviation', sa.Numeric(precision=8, scale=2), nullable=True, server_default='350'),
    )
    op.add_column(
        'competitor_stats',
        sa.Column('volatility', sa.Numeric(precision=10, scale=6), nullable=True, server_default='0.06'),
    )
    op.add_column(
        'competitor_elo_history',
        sa.Column('rd_before', sa.Numeric(precision=8, scale=2), nullable=True),
    )
    op.add_column(
        'competitor_elo_history',
        sa.Column('rd_after', sa.Numeric(precision=8, scale=2), nullable=True),
    )
    op.add_column(
        'competitor_elo_history',
        sa.Column('volatility_after', sa.Numeric(precision=10, scale=6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('competitor_elo_history', 'volatility_after')
    op.drop_column('competitor_elo_history', 'rd_after')
    op.drop_column('competitor_elo_history', 'rd_before')
    op.drop_column('competitor_stats', 'volatility')
    op.drop_column('competitor_stats', 'rating_deviation')
