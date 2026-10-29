"""Add user_bets / user_bet_legs: bets the user registers from the combo calculator.

Revision ID: e1f2a3b4c5d6
Revises: d5e6f7a8b9c0
Create Date: 2026-10-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'e1f2a3b4c5d6'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_bets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        sa.Column('amount', sa.Numeric(14, 2), nullable=False),
        sa.Column('odds', sa.Numeric(10, 3), nullable=False),
        sa.Column('probability', sa.Numeric(6, 4)),
        sa.Column('status', sa.String(10), nullable=False, server_default='PENDING'),
        sa.Column('payout_odds', sa.Numeric(10, 3)),
        sa.Column('profit', sa.Numeric(14, 2)),
        sa.Column('settled_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('PENDING', 'WON', 'LOST', 'VOID')", name='ck_user_bet_status'),
    )
    op.create_table(
        'user_bet_legs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('bet_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('user_bets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('position', sa.Integer, nullable=False, server_default='0'),
        sa.Column('match_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('matches.id'), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('selector', postgresql.JSONB, nullable=False),
        sa.Column('label', sa.String(200), nullable=False),
        sa.Column('probability', sa.Numeric(6, 4)),
        sa.Column('odds', sa.Numeric(10, 3), nullable=False),
        sa.Column('best_odds', sa.Numeric(10, 3)),
        sa.Column('status', sa.String(10), nullable=False, server_default='PENDING'),
        sa.Column('settled_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('PENDING', 'WON', 'LOST', 'VOID')", name='ck_user_bet_leg_status'),
    )
    op.create_index('ix_user_bet_legs_bet_id', 'user_bet_legs', ['bet_id'])
    op.create_index('ix_user_bet_legs_match_id', 'user_bet_legs', ['match_id'])


def downgrade() -> None:
    op.drop_index('ix_user_bet_legs_match_id', table_name='user_bet_legs')
    op.drop_index('ix_user_bet_legs_bet_id', table_name='user_bet_legs')
    op.drop_table('user_bet_legs')
    op.drop_table('user_bets')
