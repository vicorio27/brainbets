"""add natural language reasoning to predictions

Revision ID: f7a8b9c0d1e2
Revises: ded8c492bbdc
Create Date: 2026-06-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f7a8b9c0d1e2'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'predictions',
        sa.Column('natural_language_reasoning', sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('predictions', 'natural_language_reasoning')
