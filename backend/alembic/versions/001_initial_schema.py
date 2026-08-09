"""Initial schema for BrainBets PostgreSQL database.

Revision ID: 001
Revises:
Create Date: 2026-06-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    # sports
    op.create_table(
        'sports',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )

    # leagues
    op.create_table(
        'leagues',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('sport_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('country', sa.String(length=100), nullable=True),
        sa.Column('tier', sa.Integer(), nullable=True),
        sa.Column('external_id', sa.String(length=100), nullable=True),
        sa.Column('logo_url', sa.Text(), nullable=True),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['sport_id'], ['sports.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sport_id', 'external_id', name='uq_league_sport_external')
    )

    # competitors
    op.create_table(
        'competitors',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('sport_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=True),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('country', sa.String(length=100), nullable=True),
        sa.Column('external_id', sa.String(length=100), nullable=True),
        sa.Column('extra_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("type IN ('team', 'player')", name='ck_competitor_type'),
        sa.ForeignKeyConstraint(['sport_id'], ['sports.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sport_id', 'external_id', name='uq_competitor_sport_external')
    )

    # matches
    op.create_table(
        'matches',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('sport_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('league_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('season', sa.String(length=20), nullable=True),
        sa.Column('match_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=True),
        sa.Column('external_id', sa.String(length=100), nullable=True),
        sa.Column('source_api', sa.String(length=50), nullable=True),
        sa.Column('venue', sa.String(length=100), nullable=True),
        sa.Column('weather', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('extra_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_seeded', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('SCHEDULED', 'LIVE', 'FINISHED', 'POSTPONED', 'CANCELLED', 'ABANDONED')",
            name='ck_match_status'
        ),
        sa.ForeignKeyConstraint(['sport_id'], ['sports.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['league_id'], ['leagues.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # match_competitors
    op.create_table(
        'match_competitors',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('match_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('competitor_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('side', sa.String(length=10), nullable=False),
        sa.Column('pre_match_ranking', sa.Integer(), nullable=True),
        sa.Column('pre_match_form', sa.String(length=50), nullable=True),
        sa.Column('pre_match_odds', sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column('score', sa.Integer(), nullable=True),
        sa.Column('extra_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint("side IN ('home', 'away', 'player1', 'player2')", name='ck_match_competitor_side'),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['competitor_id'], ['competitors.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('match_id', 'side', name='uq_match_competitor_side')
    )

    # match_scores
    op.create_table(
        'match_scores',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('match_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('home_score', sa.Integer(), nullable=True),
        sa.Column('away_score', sa.Integer(), nullable=True),
        sa.Column('period', sa.String(length=20), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # match_events
    op.create_table(
        'match_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('match_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('period', sa.String(length=20), nullable=True),
        sa.Column('minute', sa.Integer(), nullable=True),
        sa.Column('competitor_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('extra_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['competitor_id'], ['competitors.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # competitor_stats
    op.create_table(
        'competitor_stats',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('competitor_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('league_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('season', sa.String(length=20), nullable=True),
        sa.Column('surface', sa.String(length=30), nullable=True),
        sa.Column('matches_played', sa.Integer(), nullable=True),
        sa.Column('wins', sa.Integer(), nullable=True),
        sa.Column('draws', sa.Integer(), nullable=True),
        sa.Column('losses', sa.Integer(), nullable=True),
        sa.Column('goals_for', sa.Integer(), nullable=True),
        sa.Column('goals_against', sa.Integer(), nullable=True),
        sa.Column('expected_goals', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('expected_goals_against', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('corners_avg', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('aces_avg', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('break_points_converted', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('form_string', sa.String(length=20), nullable=True),
        sa.Column('current_elo', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('current_surface_elo', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('extra_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('calculated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['competitor_id'], ['competitors.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['league_id'], ['leagues.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'competitor_id', 'league_id', 'season', 'surface',
            name='uq_competitor_stats'
        )
    )

    # competitor_elo_history
    op.create_table(
        'competitor_elo_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('competitor_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('match_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('elo_before', sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column('elo_after', sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column('surface', sa.String(length=30), nullable=True),
        sa.Column('calculated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['competitor_id'], ['competitors.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # prediction_models
    op.create_table(
        'prediction_models',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=True),
        sa.Column('sport_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('is_production', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['sport_id'], ['sports.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # model_training_runs
    op.create_table(
        'model_training_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('model_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('dataset_start_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dataset_end_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('matches_used', sa.Integer(), nullable=True),
        sa.Column('accuracy', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('log_loss', sa.Numeric(precision=8, scale=6), nullable=True),
        sa.Column('roi_simulated', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('hyperparameters', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('artifacts_path', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name='ck_training_run_status'
        ),
        sa.ForeignKeyConstraint(['model_id'], ['prediction_models.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # predictions
    op.create_table(
        'predictions',
        sa.Column('id', sa.String(length=50), primary_key=True),
        sa.Column('match_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('model_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('market', sa.String(length=50), nullable=False),
        sa.Column('predicted_outcome', sa.String(length=100), nullable=False),
        sa.Column('confidence', sa.Integer(), nullable=False),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('probabilities', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('model_contributions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('reasoning_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('expected_value', sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column('kelly_fraction', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('confidence BETWEEN 0 AND 100', name='ck_prediction_confidence'),
        sa.CheckConstraint(
            "status IN ('PENDING', 'VALIDATED', 'FAILED', 'CANCELLED')",
            name='ck_prediction_status'
        ),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['model_id'], ['prediction_models.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # prediction_results
    op.create_table(
        'prediction_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('prediction_id', sa.String(length=50), nullable=False),
        sa.Column('actual_outcome', sa.String(length=100), nullable=True),
        sa.Column('is_successful', sa.Boolean(), nullable=True),
        sa.Column('match_score_snapshot', sa.String(length=20), nullable=True),
        sa.Column('validation_notes', sa.Text(), nullable=True),
        sa.Column('validated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['prediction_id'], ['predictions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('prediction_id')
    )

    # feature_store
    op.create_table(
        'feature_store',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('match_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('competitor_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('feature_set_version', sa.String(length=20), nullable=True),
        sa.Column('features', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('target', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_training', sa.Boolean(), nullable=True),
        sa.Column('is_validation', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['competitor_id'], ['competitors.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'match_id', 'competitor_id', 'feature_set_version',
            name='uq_feature_store'
        )
    )

    # data_sources
    op.create_table(
        'data_sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=True),
        sa.Column('base_url', sa.Text(), nullable=True),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('rate_limit_per_min', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # ingestion_jobs
    op.create_table(
        'ingestion_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('data_source_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('job_type', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('records_processed', sa.Integer(), nullable=True),
        sa.Column('records_inserted', sa.Integer(), nullable=True),
        sa.Column('records_updated', sa.Integer(), nullable=True),
        sa.Column('errors', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "job_type IN ('matches', 'odds', 'statistics', 'results', 'full_sync')",
            name='ck_ingestion_job_type'
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'partial')",
            name='ck_ingestion_job_status'
        ),
        sa.ForeignKeyConstraint(['data_source_id'], ['data_sources.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # processed_files
    op.create_table(
        'processed_files',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('file_hash', sa.String(length=64), nullable=True),
        sa.Column('file_type', sa.String(length=20), nullable=True),
        sa.Column('records_inserted', sa.Integer(), nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('filename')
    )

    # audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('user_id', sa.String(length=100), nullable=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Indexes
    op.create_index('idx_matches_date', 'matches', ['match_date'], unique=False)
    op.create_index('idx_matches_status', 'matches', ['status'], unique=False)
    op.create_index('idx_matches_sport_date', 'matches', ['sport_id', 'match_date'], unique=False)
    op.create_index('idx_matches_external', 'matches', ['external_id'], unique=False)

    op.create_index('idx_match_competitors_match', 'match_competitors', ['match_id'], unique=False)
    op.create_index('idx_match_competitors_competitor', 'match_competitors', ['competitor_id'], unique=False)

    op.create_index('idx_predictions_match', 'predictions', ['match_id'], unique=False)
    op.create_index('idx_predictions_status', 'predictions', ['status'], unique=False)
    op.create_index('idx_predictions_created', 'predictions', ['created_at'], unique=False)

    op.create_index('idx_results_success', 'prediction_results', ['is_successful'], unique=False)

    op.create_index('idx_feature_store_match', 'feature_store', ['match_id'], unique=False)
    op.create_index('idx_feature_store_training', 'feature_store', ['is_training', 'is_validation'], unique=False)

    op.create_index('idx_audit_entity', 'audit_logs', ['entity_type', 'entity_id'], unique=False)
    op.create_index('idx_audit_created', 'audit_logs', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_audit_created', table_name='audit_logs')
    op.drop_index('idx_audit_entity', table_name='audit_logs')
    op.drop_index('idx_feature_store_training', table_name='feature_store')
    op.drop_index('idx_feature_store_match', table_name='feature_store')
    op.drop_index('idx_results_success', table_name='prediction_results')
    op.drop_index('idx_predictions_created', table_name='predictions')
    op.drop_index('idx_predictions_status', table_name='predictions')
    op.drop_index('idx_predictions_match', table_name='predictions')
    op.drop_index('idx_match_competitors_competitor', table_name='match_competitors')
    op.drop_index('idx_match_competitors_match', table_name='match_competitors')
    op.drop_index('idx_matches_external', table_name='matches')
    op.drop_index('idx_matches_sport_date', table_name='matches')
    op.drop_index('idx_matches_status', table_name='matches')
    op.drop_index('idx_matches_date', table_name='matches')

    op.drop_table('audit_logs')
    op.drop_table('processed_files')
    op.drop_table('ingestion_jobs')
    op.drop_table('data_sources')
    op.drop_table('feature_store')
    op.drop_table('prediction_results')
    op.drop_table('predictions')
    op.drop_table('model_training_runs')
    op.drop_table('prediction_models')
    op.drop_table('competitor_elo_history')
    op.drop_table('competitor_stats')
    op.drop_table('match_events')
    op.drop_table('match_scores')
    op.drop_table('match_competitors')
    op.drop_table('matches')
    op.drop_table('competitors')
    op.drop_table('leagues')
    op.drop_table('sports')
