"""Add LOW_CONFIDENCE prediction status.

Revision ID: 8f3e2d1c0b4a
Revises: f7a8b9c0d1e2
Create Date: 2026-06-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '8f3e2d1c0b4a'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint('ck_prediction_status', 'predictions', type_='check')
    op.create_check_constraint(
        'ck_prediction_status',
        'predictions',
        sa.text("status IN ('PENDING', 'VALIDATED', 'FAILED', 'CANCELLED', 'LOW_CONFIDENCE')"),
    )


def downgrade() -> None:
    op.drop_constraint('ck_prediction_status', 'predictions', type_='check')
    op.create_check_constraint(
        'ck_prediction_status',
        'predictions',
        sa.text("status IN ('PENDING', 'VALIDATED', 'FAILED', 'CANCELLED')"),
    )
