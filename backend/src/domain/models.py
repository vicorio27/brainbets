"""SQLAlchemy ORM models for BrainBets PostgreSQL database."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Sport(Base):
    __tablename__ = "sports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), nullable=False)
    code = Column(String(20), unique=True, nullable=False)
    config = Column(JSONB, default=dict)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    leagues = relationship("League", back_populates="sport")
    competitors = relationship("Competitor", back_populates="sport")


class League(Base):
    __tablename__ = "leagues"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sport_id = Column(UUID(as_uuid=True), ForeignKey("sports.id"), nullable=False)
    name = Column(String(100), nullable=False)
    country = Column(String(100))
    tier = Column(Integer, default=1)
    external_id = Column(String(100))
    logo_url = Column(Text)
    config = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    sport = relationship("Sport", back_populates="leagues")
    matches = relationship("Match", back_populates="league")

    __table_args__ = (UniqueConstraint("sport_id", "external_id", name="uq_league_sport_external"),)


class Competitor(Base):
    __tablename__ = "competitors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sport_id = Column(UUID(as_uuid=True), ForeignKey("sports.id"), nullable=False)
    name = Column(String(100), nullable=False)
    slug = Column(String(100))
    type = Column(String(20), nullable=False)
    country = Column(String(100))
    external_id = Column(String(100))
    extra_data = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    sport = relationship("Sport", back_populates="competitors")
    match_links = relationship("MatchCompetitor", back_populates="competitor")
    stats = relationship("CompetitorStat", back_populates="competitor")

    __table_args__ = (
        CheckConstraint("type IN ('team', 'player')", name="ck_competitor_type"),
        UniqueConstraint("sport_id", "external_id", name="uq_competitor_sport_external"),
    )


class Match(Base):
    __tablename__ = "matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sport_id = Column(UUID(as_uuid=True), ForeignKey("sports.id"), nullable=False)
    league_id = Column(UUID(as_uuid=True), ForeignKey("leagues.id"))
    season = Column(String(20))
    match_date = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(30), default="SCHEDULED")
    external_id = Column(String(100))
    source_api = Column(String(50))
    venue = Column(String(100))
    weather = Column(JSONB, default=dict)
    extra_data = Column(JSONB, default=dict)
    is_seeded = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    sport = relationship("Sport")
    league = relationship("League", back_populates="matches")
    competitors = relationship("MatchCompetitor", back_populates="match")
    scores = relationship("MatchScore", back_populates="match")
    events = relationship("MatchEvent", back_populates="match")
    predictions = relationship("Prediction", back_populates="match")

    __table_args__ = (
        CheckConstraint(
            "status IN ('SCHEDULED', 'LIVE', 'FINISHED', 'POSTPONED', 'CANCELLED', 'ABANDONED')",
            name="ck_match_status",
        ),
    )


class MatchCompetitor(Base):
    __tablename__ = "match_competitors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id = Column(UUID(as_uuid=True), ForeignKey("matches.id"), nullable=False)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id"), nullable=False)
    side = Column(String(10), nullable=False)
    pre_match_ranking = Column(Integer)
    pre_match_form = Column(String(50))
    pre_match_odds = Column(Numeric(6, 3))
    score = Column(Integer, default=0)
    extra_data = Column(JSONB, default=dict)

    match = relationship("Match", back_populates="competitors")
    competitor = relationship("Competitor", back_populates="match_links")

    __table_args__ = (
        CheckConstraint("side IN ('home', 'away', 'player1', 'player2')", name="ck_match_competitor_side"),
        UniqueConstraint("match_id", "side", name="uq_match_competitor_side"),
    )


class MatchScore(Base):
    __tablename__ = "match_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id = Column(UUID(as_uuid=True), ForeignKey("matches.id"), nullable=False)
    home_score = Column(Integer, default=0)
    away_score = Column(Integer, default=0)
    period = Column(String(20), default="FULL_TIME")
    timestamp = Column(DateTime(timezone=True), default=now_utc)

    match = relationship("Match", back_populates="scores")


class MatchEvent(Base):
    __tablename__ = "match_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id = Column(UUID(as_uuid=True), ForeignKey("matches.id"), nullable=False)
    event_type = Column(String(50), nullable=False)
    period = Column(String(20))
    minute = Column(Integer)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id"))
    description = Column(Text)
    extra_data = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    match = relationship("Match", back_populates="events")
    competitor = relationship("Competitor")


class CompetitorStat(Base):
    __tablename__ = "competitor_stats"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id"), nullable=False)
    league_id = Column(UUID(as_uuid=True), ForeignKey("leagues.id"))
    season = Column(String(20))
    surface = Column(String(30))
    matches_played = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    goals_for = Column(Integer, default=0)
    goals_against = Column(Integer, default=0)
    expected_goals = Column(Numeric(5, 2), default=0)
    expected_goals_against = Column(Numeric(5, 2), default=0)
    corners_avg = Column(Numeric(5, 2), default=0)
    aces_avg = Column(Numeric(5, 2), default=0)
    break_points_converted = Column(Numeric(5, 2), default=0)
    form_string = Column(String(20))
    current_elo = Column(Numeric(8, 2), default=1500)
    current_surface_elo = Column(Numeric(8, 2), default=1500)
    extra_data = Column(JSONB, default=dict)
    calculated_at = Column(DateTime(timezone=True), default=now_utc)

    competitor = relationship("Competitor", back_populates="stats")

    __table_args__ = (
        UniqueConstraint(
            "competitor_id",
            "league_id",
            "season",
            "surface",
            name="uq_competitor_stats",
        ),
    )


class CompetitorEloHistory(Base):
    __tablename__ = "competitor_elo_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id"), nullable=False)
    match_id = Column(UUID(as_uuid=True), ForeignKey("matches.id"))
    elo_before = Column(Numeric(8, 2), nullable=False)
    elo_after = Column(Numeric(8, 2), nullable=False)
    surface = Column(String(30))
    calculated_at = Column(DateTime(timezone=True), default=now_utc)

    competitor = relationship("Competitor")
    match = relationship("Match")


class PredictionModel(Base):
    __tablename__ = "prediction_models"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    version = Column(String(20), default="1.0")
    sport_id = Column(UUID(as_uuid=True), ForeignKey("sports.id"))
    description = Column(Text)
    config = Column(JSONB, default=dict)
    is_active = Column(Boolean, default=True)
    is_production = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    sport = relationship("Sport")
    predictions = relationship("Prediction", back_populates="model")
    training_runs = relationship("ModelTrainingRun", back_populates="model")


class ModelTrainingRun(Base):
    __tablename__ = "model_training_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id = Column(UUID(as_uuid=True), ForeignKey("prediction_models.id"), nullable=False)
    dataset_start_date = Column(DateTime(timezone=True))
    dataset_end_date = Column(DateTime(timezone=True))
    matches_used = Column(Integer, default=0)
    accuracy = Column(Numeric(5, 2))
    log_loss = Column(Numeric(8, 6))
    roi_simulated = Column(Numeric(6, 2))
    hyperparameters = Column(JSONB, default=dict)
    artifacts_path = Column(Text)
    status = Column(String(20), default="running")
    created_at = Column(DateTime(timezone=True), default=now_utc)
    completed_at = Column(DateTime(timezone=True))

    model = relationship("PredictionModel", back_populates="training_runs")

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_training_run_status",
        ),
    )


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(String(50), primary_key=True)
    match_id = Column(UUID(as_uuid=True), ForeignKey("matches.id"), nullable=False)
    model_id = Column(UUID(as_uuid=True), ForeignKey("prediction_models.id"))
    market = Column(String(50), nullable=False)
    predicted_outcome = Column(String(100), nullable=False)
    confidence = Column(Integer, nullable=False)
    reasoning = Column(Text)
    natural_language_reasoning = Column(Text)
    probabilities = Column(JSONB, default=dict)
    model_contributions = Column(JSONB, default=dict)
    reasoning_data = Column(JSONB, default=dict)
    expected_value = Column(Numeric(6, 3))
    kelly_fraction = Column(Numeric(5, 4))
    status = Column(String(20), default="PENDING")
    live_fulfillment_percent = Column(Numeric(5, 2), default=0)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    match = relationship("Match", back_populates="predictions")
    model = relationship("PredictionModel", back_populates="predictions")
    result = relationship("PredictionResult", back_populates="prediction", uselist=False)
    progress_snapshots = relationship("PredictionProgress", back_populates="prediction", order_by="PredictionProgress.snapshot_at.desc()")

    __table_args__ = (
        CheckConstraint("confidence BETWEEN 0 AND 100", name="ck_prediction_confidence"),
        CheckConstraint(
            "status IN ('PENDING', 'VALIDATED', 'FAILED', 'CANCELLED', 'LOW_CONFIDENCE')",
            name="ck_prediction_status",
        ),
    )


class PredictionResult(Base):
    __tablename__ = "prediction_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prediction_id = Column(String(50), ForeignKey("predictions.id"), nullable=False, unique=True)
    actual_outcome = Column(String(100))
    is_successful = Column(Boolean)
    match_score_snapshot = Column(String(20))
    validation_notes = Column(Text)
    validated_at = Column(DateTime(timezone=True), default=now_utc)

    prediction = relationship("Prediction", back_populates="result")


class PredictionProgress(Base):
    __tablename__ = "prediction_progress"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prediction_id = Column(String(50), ForeignKey("predictions.id"), nullable=False)
    match_id = Column(UUID(as_uuid=True), ForeignKey("matches.id"), nullable=False)
    snapshot_at = Column(DateTime(timezone=True), default=now_utc)
    minute = Column(Integer, default=0)
    period_label = Column(String(30))
    home_score = Column(Integer, default=0)
    away_score = Column(Integer, default=0)
    fulfillment_percent = Column(Numeric(5, 2), default=0)
    notes = Column(Text)

    prediction = relationship("Prediction", back_populates="progress_snapshots")
    match = relationship("Match")


class FeatureStore(Base):
    __tablename__ = "feature_store"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id = Column(UUID(as_uuid=True), ForeignKey("matches.id"), nullable=False)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id"), nullable=False)
    feature_set_version = Column(String(20), default="v1")
    features = Column(JSONB, nullable=False)
    target = Column(JSONB)
    is_training = Column(Boolean, default=False)
    is_validation = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    match = relationship("Match")
    competitor = relationship("Competitor")

    __table_args__ = (
        UniqueConstraint(
            "match_id",
            "competitor_id",
            "feature_set_version",
            name="uq_feature_store",
        ),
    )


class DataSource(Base):
    __tablename__ = "data_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), nullable=False)
    provider = Column(String(50))
    base_url = Column(Text)
    api_key_encrypted = Column(Text)
    rate_limit_per_min = Column(Integer, default=60)
    is_active = Column(Boolean, default=True)
    config = Column(JSONB, default=dict)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    data_source_id = Column(UUID(as_uuid=True), ForeignKey("data_sources.id"))
    job_type = Column(String(30), nullable=False)
    status = Column(String(20), default="running")
    params = Column(JSONB, default=dict)
    records_processed = Column(Integer, default=0)
    records_inserted = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    errors = Column(JSONB, default=list)
    started_at = Column(DateTime(timezone=True), default=now_utc)
    completed_at = Column(DateTime(timezone=True))

    data_source = relationship("DataSource")

    __table_args__ = (
        CheckConstraint(
            "job_type IN ('matches', 'odds', 'statistics', 'results', 'full_sync')",
            name="ck_ingestion_job_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'partial')",
            name="ck_ingestion_job_status",
        ),
    )


class ProcessedFile(Base):
    __tablename__ = "processed_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), unique=True, nullable=False)
    file_hash = Column(String(64))
    file_type = Column(String(20))  # matches, predictions, results
    records_inserted = Column(Integer, default=0)
    processed_at = Column(DateTime(timezone=True), default=now_utc)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(String(50), nullable=False)
    user_id = Column(String(100))
    payload = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=now_utc)


class ExternalApiCache(Base):
    __tablename__ = "external_api_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url = Column(Text, nullable=False)
    method = Column(String(10), default="GET", nullable=False)
    response_json = Column(JSONB, default=dict)
    status_code = Column(Integer, default=200)
    cached_at = Column(DateTime(timezone=True), default=now_utc)
    expires_at = Column(DateTime(timezone=True), default=now_utc)
    hit_count = Column(Integer, default=0)

    __table_args__ = (UniqueConstraint("url", "method", name="uq_external_api_cache_url_method"),)
