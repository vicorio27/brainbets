"""shift match dates stored as naive Bogota wall-clock time to real UTC

Every writer of `matches.match_date` (live collect via /matches/bulk, the
backfill, migration_worker, historical ingestion) handed PostgreSQL a naive
datetime that was really America/Bogota wall-clock time (or a bare calendar
date). The column is timestamptz and the session runs in UTC, so each value
was stored 5 hours too early. Verified 2026-10-10 against api-tennis: for 28
fixtures the stored UTC numerals equalled the API's Bogota local time.

Bogota has no DST, so the correction is a uniform +5h. Every row gets it --
that keeps all relative ordering (Elo, features, "before this match") intact.
`competitor_elo_history.calculated_at` is a copy of the match date for all
rows, so it moves with it; otherwise a match's own post-match Elo row would
suddenly look like it predates the match.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-10-10
"""
from alembic import op

revision = 'd5e6f7a8b9c0'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE matches SET match_date = match_date + interval '5 hours'")
    op.execute("UPDATE competitor_elo_history SET calculated_at = calculated_at + interval '5 hours'")


def downgrade() -> None:
    op.execute("UPDATE matches SET match_date = match_date - interval '5 hours'")
    op.execute("UPDATE competitor_elo_history SET calculated_at = calculated_at - interval '5 hours'")
