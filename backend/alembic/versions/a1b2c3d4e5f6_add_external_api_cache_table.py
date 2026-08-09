"""add external api cache table

Revision ID: a1b2c3d4e5f6
Revises: ded8c492bbdc
Create Date: 2026-06-21 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'ded8c492bbdc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'external_api_cache',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('method', sa.String(length=10), nullable=False, server_default='GET'),
        sa.Column('response_json', postgresql.JSONB(astext_type=sa.Text()), default=dict),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('cached_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('hit_count', sa.Integer(), nullable=True, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('url', 'method', name='uq_external_api_cache_url_method')
    )
    op.create_index('idx_external_api_cache_expires', 'external_api_cache', ['expires_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_external_api_cache_expires', table_name='external_api_cache')
    op.drop_table('external_api_cache')
