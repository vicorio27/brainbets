"""Internal API endpoints used by n8n workflows and migration workers.

These endpoints are protected by an API key and are not exposed to the public.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
import json
import logging
import os
import requests
import time

from src.application.elo_service import run_elo_training
from src.application.feature_service import FeatureService
from src.application.football_stats_service import enrich_football_match
from src.application.tennis_stats_service import (
    compute_tennis_h2h,
    enrich_tennis_match,
    resolve_competitor_fuzzy,
)
from src.application.historical_ingestion import run_full_ingestion
from src.application.poisson_service import run_poisson_training
from src.timezone import BOGOTA_TZ, today_bogota
from src.application.progress_service import process_snapshots
from src.application.services import DataService
from src.application.tennis_ml_service import (
    predict_tennis_ml,
    predict_tennis_ml_batch,
    train_tennis_ml_model,
)
from src.application.validation_service import validate_pending_predictions
from src.presentation.schemas import ScoresBulkPayload, SnapshotsPayload
from src.domain.models import (
    Competitor,
    ExternalApiCache,
    IngestionJob,
    League,
    Match,
    MatchCompetitor,
    MatchScore,
    Prediction,
    PredictionModel,
    PredictionResult,
    ProcessedFile,
    Sport,
)
from src.infrastructure.database import get_db
from src.presentation.dependencies import verify_internal_api_key
from src.presentation.schemas import ApiCacheStoreRequest


LOW_CONFIDENCE_THRESHOLD = int(os.environ.get("LOW_CONFIDENCE_THRESHOLD", "55"))


class MatchesFilePayload(BaseModel):
    generatedAt: str
    source: Optional[str] = "live_api"
    tennis: List[Dict[str, Any]] = []
    football: List[Dict[str, Any]] = []


class FootballEnrichPayload(BaseModel):
    matchIds: List[str] = []


class TennisEnrichPayload(BaseModel):
    matches: List[Dict[str, Any]] = []


class PredictionsFilePayload(BaseModel):
    generatedAt: str
    source: Optional[str] = "prediction_engine_openai"
    predictions: List[Dict[str, Any]] = []


class ResultsFilePayload(BaseModel):
    generatedAt: str
    source: Optional[str] = "validation_pipeline"
    results: List[Dict[str, Any]] = []


class BulkResponse(BaseModel):
    inserted: int
    updated: int
    errors: List[str]


class ProxyRequest(BaseModel):
    url: str
    method: Optional[str] = "GET"
    headers: Optional[Dict[str, str]] = {}
    ttlSeconds: Optional[int] = 60
    maxRetries: Optional[int] = 3
    unwrap: Optional[bool] = True


def _normalize_status(status: Optional[str]) -> str:
    if not status:
        return "SCHEDULED"
    status_upper = status.upper()
    # Explicit live indicators
    if any(k in status_upper for k in ("LIVE", "1H", "2H", "HT", "HALF", "IN PROGRESS", "ONGOING", "1ST HALF", "2ND HALF")):
        return "LIVE"
    # Minute markers like "78'", "45+2'", "HT" indicate a live match
    if "'" in status or "+" in status:
        return "LIVE"
    if any(k in status_upper for k in ("FINISHED", "FT", "FULL", "ENDED", "POSTPONED", "CANCELLED", "ABANDONED")):
        return "FINISHED" if "POSTPONED" not in status_upper and "CANCELLED" not in status_upper and "ABANDONED" not in status_upper else status_upper
    if status.strip() == "-":
        return "FINISHED"
    return "SCHEDULED"


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # Handle common ISO formats
        value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except Exception:
        return datetime.now(timezone.utc)


def _ensure_sport(db: Session, code: str, name: str) -> Sport:
    sport = db.query(Sport).filter(Sport.code == code).first()
    if not sport:
        sport = Sport(id=uuid4(), code=code, name=name)
        db.add(sport)
        db.commit()
        db.refresh(sport)
    return sport


def _ensure_league(
    db: Session,
    sport_id: str,
    name: str,
    external_id: Optional[str] = None,
    tier: Optional[int] = None,
) -> League:
    league = (
        db.query(League)
        .filter(League.sport_id == sport_id, League.name == name)
        .first()
    )
    if not league:
        league = League(
            id=uuid4(),
            sport_id=sport_id,
            name=name,
            external_id=external_id,
            tier=tier if tier is not None else 5,
        )
        db.add(league)
        db.commit()
        db.refresh(league)
    elif tier is not None:
        league.tier = tier
        db.commit()
        db.refresh(league)
    return league


def _ensure_competitor(
    db: Session,
    sport_id: str,
    name: str,
    competitor_type: str,
    external_id: Optional[str] = None,
    country: Optional[str] = None,
) -> Competitor:
    competitor = (
        db.query(Competitor)
        .filter(
            Competitor.sport_id == sport_id,
            Competitor.name.ilike(name),
            Competitor.type == competitor_type,
        )
        .first()
    )
    if not competitor and competitor_type == "player":
        # Tennis providers send abbreviated names ('T. M. Etcheverry'). Link
        # them to the existing full-name competitor so Elo, form and H2H
        # features stay connected to the historical record.
        fuzzy = resolve_competitor_fuzzy(db, sport_id, name)
        if fuzzy is not None and fuzzy.type == competitor_type:
            competitor = fuzzy
    if not competitor:
        competitor = Competitor(
            id=uuid4(),
            sport_id=sport_id,
            name=name,
            type=competitor_type,
            external_id=external_id,
            country=country,
        )
        db.add(competitor)
        db.commit()
        db.refresh(competitor)
    elif country and not competitor.country:
        competitor.country = country
        db.commit()
        db.refresh(competitor)
    return competitor


def _parse_odds(value: Any) -> Optional[float]:
    """Parse an odds value into a float, returning None for invalid values."""
    if value is None or value == "":
        return None
    try:
        odds = float(value)
        return odds if odds > 1.0 else None
    except (TypeError, ValueError):
        return None


def _insert_match(
    db: Session,
    sport_code: str,
    sport_name: str,
    competitor_type: str,
    raw: Dict[str, Any],
    side_mapping: Dict[str, str],
    generated_at: datetime,
    source_api: Optional[str] = None,
) -> Optional[str]:
    """Insert a single match with competitors. Returns match ID or None on error."""
    try:
        sport = _ensure_sport(db, sport_code, sport_name)

        # Extract league/tournament name
        league_name = raw.get("league") or raw.get("tournament") or "Unknown"
        league_tier = raw.get("leagueTier") if raw.get("leagueTier") is not None else raw.get("tournamentTier")
        league = _ensure_league(db, sport.id, league_name, external_id=raw.get("eventId"), tier=league_tier)

        match_id = raw.get("matchId") or str(uuid4())
        match_external_id = match_id or (str(raw.get("eventId")) if raw.get("eventId") else None)

        match_date = _parse_iso_datetime(raw.get("eventDate"))
        if raw.get("eventTime") and match_date:
            try:
                hour, minute = raw["eventTime"].split(":")[:2]
                match_date = match_date.replace(hour=int(hour), minute=int(minute))
            except Exception:
                pass

        # Upsert match
        match = (
            db.query(Match)
            .filter(Match.external_id == match_external_id, Match.sport_id == sport.id)
            .first()
        )
        if not match:
            match = Match(
                id=uuid4(),
                sport_id=sport.id,
                league_id=league.id,
                external_id=match_external_id,
                source_api=source_api or "rapidapi",
                match_date=match_date or generated_at,
                status=_normalize_status(raw.get("status")),
                extra_data={
                    "surface": raw.get("surface"),
                    "h2h": raw.get("h2h"),
                    "source": raw.get("source", "live_api"),
                    "draw_odds": _parse_odds(raw.get("drawOdds")),
                    "home_xg_against": raw.get("homeXgAgainst"),
                    "away_xg_against": raw.get("awayXgAgainst"),
                    "head_to_head": raw.get("headToHead"),
                    "home_form_stats": raw.get("homeFormStats"),
                    "away_form_stats": raw.get("awayFormStats"),
                    "league_standings": raw.get("leagueStandings"),
                    "stats_data_quality": raw.get("statsDataQuality"),
                    "tournament_tier": raw.get("tournamentTier"),
                    "ground_type": raw.get("groundType"),
                    "expert_consensus": raw.get("expertConsensus"),
                },
                created_at=generated_at,
            )
            db.add(match)
            db.commit()
            db.refresh(match)
        else:
            match.match_date = match_date or match.match_date
            match.status = _normalize_status(raw.get("status")) if raw.get("status") else match.status
            # Only apply H2H data to NEW matches. On updates we keep the existing
            # h2h/head_to_head value (even if null) to avoid burning API calls on
            # already-collected events.
            existing_extra = match.extra_data or {}
            match.extra_data = {
                **existing_extra,
                "surface": raw.get("surface"),
                "draw_odds": _parse_odds(raw.get("drawOdds")),
                "home_xg_against": raw.get("homeXgAgainst"),
                "away_xg_against": raw.get("awayXgAgainst"),
                "home_form_stats": raw.get("homeFormStats"),
                "away_form_stats": raw.get("awayFormStats"),
                "league_standings": raw.get("leagueStandings"),
                "stats_data_quality": raw.get("statsDataQuality"),
                "tournament_tier": raw.get("tournamentTier"),
                "ground_type": raw.get("groundType"),
                "expert_consensus": raw.get("expertConsensus")
                if raw.get("expertConsensus") is not None
                else existing_extra.get("expert_consensus"),
            }
            db.commit()
            db.refresh(match)

        # Insert/Update competitors
        for side_key, side_name in side_mapping.items():
            name = raw.get(side_key)
            if not name:
                continue
            country_key = None
            if sport_code == "football":
                country_key = "homeCountry" if side_key in ("homeTeam",) else "awayCountry"
            else:
                country_key = "countryPlayer1" if side_key == "player1" else "countryPlayer2"
            competitor = _ensure_competitor(
                db, sport.id, name, competitor_type, country=raw.get(country_key)
            )

            metadata = {}
            if sport_code == "football":
                prefix = "home" if side_key in ("homeTeam",) else "away"
                metadata = {
                    "expected_goals": raw.get(f"{prefix}Xg") or raw.get(f"{prefix}_xg"),
                    "corners_avg": raw.get(f"{prefix}Corners") or raw.get(f"{prefix}_corners"),
                }
            elif sport_code == "tennis":
                prefix = "player1" if side_key == "player1" else "player2"
                metadata = {
                    "aces_avg": raw.get(f"{prefix}AcesAvg") or raw.get(f"aces_avg_{prefix}"),
                }

            ranking_key = None
            if sport_code == "football":
                ranking_key = "homePosition" if side_key in ("homeTeam",) else "awayPosition"
            else:
                ranking_key = "rankingPlayer1" if side_key == "player1" else "rankingPlayer2"

            form_key = None
            if sport_code == "football":
                form_key = "homeForm" if side_key in ("homeTeam",) else "awayForm"
            else:
                form_key = "formPlayer1" if side_key == "player1" else "formPlayer2"

            odds_key = None
            if sport_code == "football":
                odds_key = "homeOdds" if side_key in ("homeTeam",) else "awayOdds"
            elif sport_code == "tennis":
                odds_key = "oddsPlayer1" if side_key == "player1" else "oddsPlayer2"

            link = (
                db.query(MatchCompetitor)
                .filter(MatchCompetitor.match_id == match.id, MatchCompetitor.side == side_name)
                .first()
            )

            if not link:
                link = MatchCompetitor(
                    id=uuid4(),
                    match_id=match.id,
                    competitor_id=competitor.id,
                    side=side_name,
                    pre_match_ranking=raw.get(ranking_key),
                    pre_match_form=raw.get(form_key) if raw.get(form_key) != 'N/A' else None,
                    pre_match_odds=_parse_odds(raw.get(odds_key)) if odds_key else None,
                    extra_data=metadata,
                )
                db.add(link)
            else:
                link.pre_match_ranking = raw.get(ranking_key, link.pre_match_ranking)
                link.pre_match_form = raw.get(form_key, link.pre_match_form)
                if link.pre_match_form == 'N/A':
                    link.pre_match_form = None
                if odds_key:
                    parsed_odds = _parse_odds(raw.get(odds_key))
                    if parsed_odds is not None:
                        link.pre_match_odds = parsed_odds
                link.extra_data = {**(link.extra_data or {}), **metadata}
            db.commit()

        # Insert score if available. Only FINAL results are accepted here:
        # collection payloads may carry placeholder 0-0 scores for matches
        # that have not started (e.g. football fixtures), which must never
        # be persisted as FULL_TIME results.
        if (
            "homeScore" in raw
            and "awayScore" in raw
            and (raw.get("status") or "").upper() == "FINISHED"
        ):
            score = (
                db.query(MatchScore)
                .filter(MatchScore.match_id == match.id, MatchScore.period == "FULL_TIME")
                .first()
            )
            if not score:
                score = MatchScore(
                    id=uuid4(),
                    match_id=match.id,
                    home_score=int(raw["homeScore"]) if raw["homeScore"] else 0,
                    away_score=int(raw["awayScore"]) if raw["awayScore"] else 0,
                    period="FULL_TIME",
                )
                db.add(score)
                db.commit()
            else:
                score.home_score = int(raw["homeScore"]) if raw["homeScore"] else score.home_score
                score.away_score = int(raw["awayScore"]) if raw["awayScore"] else score.away_score
                db.commit()

        return str(match.id)
    except Exception as e:
        db.rollback()
        return None


def get_router() -> APIRouter:
    r = APIRouter(prefix="", tags=["internal"], dependencies=[Depends(verify_internal_api_key)])

    @r.post("/matches/bulk", response_model=BulkResponse)
    async def create_matches_bulk(
        payload: MatchesFilePayload,
        db: Session = Depends(get_db),
    ):
        inserted = 0
        updated = 0
        errors = []

        generated_at = _parse_iso_datetime(payload.generatedAt) or datetime.now(timezone.utc)

        for raw in payload.football:
            match_id = _insert_match(
                db,
                sport_code="football",
                sport_name="Football",
                competitor_type="team",
                raw=raw,
                side_mapping={"homeTeam": "home", "awayTeam": "away"},
                generated_at=generated_at,
                source_api=payload.source,
            )
            if match_id:
                inserted += 1
            else:
                errors.append(f"Failed to insert football match: {raw.get('matchId')}")

        for raw in payload.tennis:
            match_id = _insert_match(
                db,
                sport_code="tennis",
                sport_name="Tennis",
                competitor_type="player",
                raw=raw,
                side_mapping={"player1": "player1", "player2": "player2"},
                generated_at=generated_at,
                source_api=payload.source,
            )
            if match_id:
                inserted += 1
            else:
                errors.append(f"Failed to insert tennis match: {raw.get('matchId')}")

        return BulkResponse(inserted=inserted, updated=updated, errors=errors)

    @r.post("/matches/scores/bulk", response_model=BulkResponse)
    async def update_match_scores_bulk(
        payload: ScoresBulkPayload,
        db: Session = Depends(get_db),
    ):
        """Upsert final scores for matches by external_id."""
        inserted = 0
        updated = 0
        errors = []

        for item in payload.scores:
            try:
                match = db.query(Match).filter(Match.external_id == item.matchId).first()
                if not match:
                    errors.append(f"Match not found: {item.matchId}")
                    continue

                score = (
                    db.query(MatchScore)
                    .filter(MatchScore.match_id == match.id, MatchScore.period == (item.period or "FULL_TIME"))
                    .first()
                )
                if not score:
                    score = MatchScore(
                        id=uuid4(),
                        match_id=match.id,
                        home_score=item.homeScore,
                        away_score=item.awayScore,
                        period=item.period or "FULL_TIME",
                    )
                    db.add(score)
                    inserted += 1
                else:
                    score.home_score = item.homeScore
                    score.away_score = item.awayScore
                    updated += 1

                if item.status:
                    match.status = item.status.upper()

                # Preserve optional per-score statistics (e.g. tennis per-set
                # games, points, aces). Rebuild extra_data as a new dict so
                # SQLAlchemy detects the change on the JSON column (in-place
                # mutation of the existing dict is not tracked).
                if item.extraData:
                    existing = match.extra_data or {}
                    match.extra_data = {
                        **existing,
                        "score_stats": {
                            **(existing.get("score_stats") or {}),
                            **item.extraData,
                        },
                    }

                db.commit()
            except Exception as e:
                db.rollback()
                errors.append(f"Failed to update score for {item.matchId}: {str(e)}")

        return BulkResponse(inserted=inserted, updated=updated, errors=errors)

    @r.post("/matches/football/enrich")
    async def enrich_football_matches(
        payload: FootballEnrichPayload,
        db: Session = Depends(get_db),
    ):
        """Enrich football matches with real computed stats from historical data."""
        sport = db.query(Sport).filter(Sport.code == "football").first()
        if not sport:
            return {"status": "error", "message": "Football sport not found"}

        results = {}
        query = db.query(Match).filter(Match.sport_id == sport.id)
        if payload.matchIds:
            query = query.filter(Match.external_id.in_(payload.matchIds))
        else:
            # Default to upcoming/scheduled matches.
            query = query.filter(Match.status.in_(["SCHEDULED", "LIVE"]))

        matches = query.all()
        for match in matches:
            try:
                stats = enrich_football_match(db, match)
                results[match.external_id or str(match.id)] = stats
            except Exception as e:
                results[match.external_id or str(match.id)] = {
                    "error": str(e),
                    "dataQuality": "fallback",
                }

        return {
            "status": "success",
            "enriched": len(results),
            "stats": results,
        }

    @r.post("/matches/tennis/enrich")
    async def enrich_tennis_matches(
        payload: TennisEnrichPayload,
        db: Session = Depends(get_db),
    ):
        """Enrich tennis matches with H2H and FeatureService-derived stats."""
        results = {}
        for raw in payload.matches:
            match_id = raw.get("matchId")
            player1 = raw.get("player1")
            player2 = raw.get("player2")
            if not match_id or not player1 or not player2:
                continue

            try:
                results[match_id] = enrich_tennis_match(db, raw)
            except Exception:
                results[match_id] = None

        return {
            "status": "success",
            "enriched": len(results),
            "stats": results,
        }

    @r.post("/predictions/bulk", response_model=BulkResponse)
    async def create_predictions_bulk(
        payload: PredictionsFilePayload,
        db: Session = Depends(get_db),
    ):
        inserted = 0
        updated = 0
        errors = []

        logging.warning(f"[BULK] received {len(payload.predictions)} predictions, generatedAt={payload.generatedAt}")

        generated_at = _parse_iso_datetime(payload.generatedAt) or datetime.now(timezone.utc)

        for raw in payload.predictions:
            try:
                match_id_str = raw.get("matchId")
                if not match_id_str:
                    errors.append("Prediction missing matchId")
                    continue

                # Find match by external_id
                match = db.query(Match).filter(Match.external_id == str(match_id_str)).first()
                if not match:
                    errors.append(f"Match not found for prediction: {match_id_str}")
                    continue

                # Default model: OpenAI Ensemble
                model = db.query(PredictionModel).filter(PredictionModel.name == "OpenAI Ensemble").first()
                if not model:
                    model = PredictionModel(id=uuid4(), name="OpenAI Ensemble", version="1.0")
                    db.add(model)
                    db.commit()
                    db.refresh(model)

                prediction_id = raw.get("predictionId") or str(uuid4())
                confidence = raw.get("confidence", 0) or 0
                pred_status = raw.get("status", "PENDING")
                if pred_status == "PENDING" and confidence < LOW_CONFIDENCE_THRESHOLD:
                    pred_status = "LOW_CONFIDENCE"

                prediction = db.query(Prediction).filter(Prediction.id == prediction_id).first()
                if not prediction:
                    prediction = Prediction(
                        id=prediction_id,
                        match_id=match.id,
                        model_id=model.id,
                        market=raw.get("market", "Unknown"),
                        predicted_outcome=raw.get("prediction", ""),
                        confidence=confidence,
                        reasoning=raw.get("reasoning", ""),
                        natural_language_reasoning=raw.get("naturalLanguageReasoning", ""),
                        probabilities=raw.get("probabilities", {}),
                        model_contributions=raw.get("modelContributions", {}),
                        reasoning_data=raw.get("reasoningData", {}),
                        expected_value=raw.get("expectedValue"),
                        kelly_fraction=raw.get("kellyFraction"),
                        status=pred_status,
                        created_at=generated_at,
                    )
                    db.add(prediction)
                    inserted += 1
                else:
                    prediction.match_id = match.id
                    prediction.market = raw.get("market", prediction.market)
                    prediction.predicted_outcome = raw.get("prediction", prediction.predicted_outcome)
                    prediction.confidence = confidence
                    prediction.reasoning = raw.get("reasoning", prediction.reasoning)
                    prediction.natural_language_reasoning = raw.get("naturalLanguageReasoning", prediction.natural_language_reasoning)
                    prediction.probabilities = raw.get("probabilities", prediction.probabilities)
                    prediction.model_contributions = raw.get("modelContributions", prediction.model_contributions)
                    prediction.reasoning_data = raw.get("reasoningData", prediction.reasoning_data)
                    if raw.get("expectedValue") is not None:
                        prediction.expected_value = raw.get("expectedValue")
                    if raw.get("kellyFraction") is not None:
                        prediction.kelly_fraction = raw.get("kellyFraction")
                    prediction.status = pred_status
                    updated += 1

                db.commit()
            except Exception as e:
                db.rollback()
                errors.append(f"Failed to insert prediction {raw.get('predictionId')}: {str(e)}")

        return BulkResponse(inserted=inserted, updated=updated, errors=errors)

    @r.post("/results/bulk", response_model=BulkResponse)
    async def create_results_bulk(
        payload: ResultsFilePayload,
        db: Session = Depends(get_db),
    ):
        inserted = 0
        updated = 0
        errors = []

        generated_at = _parse_iso_datetime(payload.generatedAt) or datetime.now(timezone.utc)

        for raw in payload.results:
            try:
                prediction_id_str = raw.get("predictionId")
                if not prediction_id_str:
                    errors.append("Result missing predictionId")
                    continue

                prediction = db.query(Prediction).filter(Prediction.id == prediction_id_str).first()
                if not prediction:
                    errors.append(f"Prediction not found for result: {prediction_id_str}")
                    continue

                result = (
                    db.query(PredictionResult)
                    .filter(PredictionResult.prediction_id == prediction.id)
                    .first()
                )
                if not result:
                    result = PredictionResult(
                        id=uuid4(),
                        prediction_id=prediction.id,
                        actual_outcome=raw.get("actualResult"),
                        is_successful=raw.get("success"),
                        match_score_snapshot=raw.get("matchScore") or raw.get("match_score_snapshot"),
                        validation_notes=raw.get("validationReason") or raw.get("validation_reason"),
                        validated_at=generated_at,
                    )
                    db.add(result)
                    inserted += 1
                else:
                    result.actual_outcome = raw.get("actualResult", result.actual_outcome)
                    result.is_successful = raw.get("success", result.is_successful)
                    result.match_score_snapshot = raw.get("matchScore") or raw.get("match_score_snapshot", result.match_score_snapshot)
                    result.validation_notes = raw.get("validationReason") or raw.get("validation_reason", result.validation_notes)
                    result.validated_at = generated_at
                    updated += 1

                prediction.status = "VALIDATED" if result.is_successful is True else "FAILED" if result.is_successful is False else prediction.status
                db.commit()
            except Exception as e:
                db.rollback()
                errors.append(f"Failed to insert result {raw.get('predictionId')}: {str(e)}")

        return BulkResponse(inserted=inserted, updated=updated, errors=errors)

    @r.post("/processed-files")
    async def mark_files_processed(
        filenames: List[str],
        db: Session = Depends(get_db),
    ):
        """Mark files as processed (used by migration worker)."""
        for filename in filenames:
            existing = db.query(ProcessedFile).filter(ProcessedFile.filename == filename).first()
            if not existing:
                db.add(ProcessedFile(filename=filename, processed_at=datetime.now(timezone.utc)))
        db.commit()
        return {"processed": len(filenames)}

    @r.post("/ingestion/jobs")
    async def create_ingestion_job(
        payload: Dict[str, Any],
        db: Session = Depends(get_db),
    ):
        job = IngestionJob(
            id=uuid4(),
            job_type=payload.get("job_type", "full_sync"),
            status=payload.get("status", "running"),
            params=payload.get("params", {}),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return {"id": str(job.id), "status": job.status}

    @r.post("/ingest/historical")
    async def ingest_historical(
        payload: Dict[str, Any],
        db: Session = Depends(get_db),
    ):
        """Trigger historical data ingestion.

        Payload example:
        {
            "tennis_years": [2010, 2011, 2012],
            "football_seasons": [["1011", "E0"], ["1112", "E0"]],
            "force_download": false
        }
        """
        tennis_years = payload.get("tennis_years", [])
        football_seasons = payload.get("football_seasons", [])
        force_download = payload.get("force_download", False)

        summary = run_full_ingestion(
            db,
            tennis_years=tennis_years,
            football_seasons=football_seasons,
            force_download=force_download,
        )
        return summary

    @r.post("/train/models")
    async def train_models(
        payload: Dict[str, Any],
        db: Session = Depends(get_db),
    ):
        """Train Elo, Poisson and tennis ML models from historical matches.

        Payload example:
        {
            "sports": ["football", "tennis"],
            "run_elo": true,
            "run_poisson": true,
            "run_tennis_ml": true
        }
        """
        sports = payload.get("sports", ["football", "tennis"])
        run_elo = payload.get("run_elo", True)
        run_poisson_flag = payload.get("run_poisson", True)
        run_tennis_ml = payload.get("run_tennis_ml", True)

        result = {}
        if run_elo:
            result["elo"] = run_elo_training(db, sports=sports)
        if run_poisson_flag:
            result["poisson"] = run_poisson_training(db)
        if run_tennis_ml:
            result["tennis_ml"] = train_tennis_ml_model(db)

        return result

    @r.post("/train/calibration")
    async def train_calibration_endpoint(
        db: Session = Depends(get_db),
    ):
        """Recompute confidence calibration curves from validated outcomes.

        Fits binned curves per (sport, market) with sport/global fallbacks and
        stores them in /storage/models/calibration.json. The public predictions
        API serves calibratedConfidence/calibratedExpectedValue from that
        artifact (no redeploy needed after retraining).
        """
        from src.application.calibration_service import train_calibration

        return train_calibration(db)

    @r.post("/predict/tennis-ml")
    async def predict_tennis_ml_endpoint(
        payload: Dict[str, Any],
    ):
        """Return player1/player2 win probabilities from the trained tennis ML model.

        Payload example (all 11 features; omitted values use defaults):
        {
            "elo_diff": 120.5,
            "surface_elo_diff": 80.0,
            "rank_diff": -50,
            "p1_recent_win_rate": 0.7,
            "p2_recent_win_rate": 0.4,
            "surface_p1_recent_win_rate": 0.8,
            "surface_p2_recent_win_rate": 0.3,
            "p1_days_since_last_match": 5.0,
            "p2_days_since_last_match": 12.0,
            "p1_matches_last_30_days": 4,
            "p2_matches_last_30_days": 1
        }
        """
        probs = predict_tennis_ml(payload)
        if probs is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Tennis ML model not available. Run /train/models first.",
            )
        return {"probabilities": probs}

    @r.post("/predict/tennis-ml/batch")
    async def predict_tennis_ml_batch_endpoint(
        payload: Dict[str, Any],
    ):
        """Return player1/player2 probabilities for a batch of matches.

        Payload example:
        {
            "matches": [
                {"eloPlayer1": 1800, "eloPlayer2": 1700, ...},
                ...
            ]
        }
        """
        matches = payload.get("matches", [])
        if not matches:
            return {"probabilities": []}

        probs = predict_tennis_ml_batch(matches)
        if probs is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Tennis ML model not available. Run /train/models first.",
            )
        return {"probabilities": probs}

    @r.post("/validate/predictions")
    async def validate_predictions(
        sport: Optional[str] = Query(None, description="Validate only predictions for this sport code (football, tennis)"),
        db: Session = Depends(get_db),
    ):
        """Validate pending predictions against match results in the DB.

        For finished matches with final scores, determines the actual outcome
        and marks each prediction as VALIDATED/FAILED. Matches still live or
        without a score remain PENDING.

        If sport is provided, only predictions for that sport are validated.
        """
        return validate_pending_predictions(db, sport=sport)

    @r.post("/predictions/progress")
    async def record_prediction_progress(
        payload: SnapshotsPayload,
        db: Session = Depends(get_db),
    ):
        """Record live snapshots and update per-prediction fulfillment percent.

        Snapshots can be sent from the `update_scores` workflow for any sport.
        Each pending prediction linked to the match gets a new progress row and
        its `live_fulfillment_percent` is updated.
        """
        snapshots = [s.model_dump() for s in payload.snapshots]
        return process_snapshots(db, snapshots)

    @r.get("/cache")
    async def get_cached_response(
        url: str,
        method: Optional[str] = "GET",
        db: Session = Depends(get_db),
    ):
        """Return a cached external API response if it has not expired."""
        now = datetime.now(timezone.utc)
        entry = (
            db.query(ExternalApiCache)
            .filter(
                ExternalApiCache.url == url,
                ExternalApiCache.method == method.upper(),
                ExternalApiCache.expires_at > now,
            )
            .first()
        )
        if entry:
            entry.hit_count = (entry.hit_count or 0) + 1
            db.commit()
            return {
                "cached": True,
                "entry": {
                    "url": entry.url,
                    "method": entry.method,
                    "responseJson": entry.response_json,
                    "statusCode": entry.status_code,
                    "cachedAt": entry.cached_at.isoformat() if entry.cached_at else None,
                    "expiresAt": entry.expires_at.isoformat() if entry.expires_at else None,
                    "hitCount": entry.hit_count,
                },
            }
        return {"cached": False, "entry": None}

    @r.post("/cache")
    async def store_cached_response(
        payload: ApiCacheStoreRequest,
        db: Session = Depends(get_db),
    ):
        """Cache an external API response with a TTL to reduce rate-limit hits."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=payload.ttlSeconds or 60)
        entry = (
            db.query(ExternalApiCache)
            .filter(
                ExternalApiCache.url == payload.url,
                ExternalApiCache.method == payload.method.upper(),
            )
            .first()
        )
        if entry:
            entry.response_json = payload.responseJson
            entry.status_code = payload.statusCode
            entry.cached_at = now
            entry.expires_at = expires
            entry.hit_count = 0
        else:
            entry = ExternalApiCache(
                id=uuid4(),
                url=payload.url,
                method=payload.method.upper(),
                response_json=payload.responseJson,
                status_code=payload.statusCode,
                cached_at=now,
                expires_at=expires,
                hit_count=0,
            )
            db.add(entry)
        db.commit()
        return {
            "cached": True,
            "expiresAt": entry.expires_at.isoformat(),
        }

    @r.post("/proxy")
    async def proxy_external_request(
        payload: ProxyRequest,
        db: Session = Depends(get_db),
    ):
        """Proxy external API calls with PostgreSQL-backed caching and 429 backoff.

        n8n workflows should call this endpoint instead of hitting RapidAPI
        directly. Cached 2xx responses are returned immediately; 429 responses
        are retried with exponential backoff before giving up.
        """
        method = (payload.method or "GET").upper()
        now = datetime.now(timezone.utc)

        # Try cache first
        cached = (
            db.query(ExternalApiCache)
            .filter(
                ExternalApiCache.url == payload.url,
                ExternalApiCache.method == method,
                ExternalApiCache.expires_at > now,
            )
            .first()
        )
        if cached:
            cached.hit_count = (cached.hit_count or 0) + 1
            db.commit()
            if payload.unwrap:
                # When unwrapping, always return 200 with a JSON body so n8n HTTP Request
                # nodes don't fail on cached upstream 4xx/5xx/204 responses. Workflows
                # inspect the payload and handle errors/missing fields in Code nodes.
                content = json.dumps(cached.response_json, ensure_ascii=False).encode("utf-8")
                return Response(
                    content=content,
                    media_type="application/json",
                    headers={
                        "X-Cache": "HIT",
                        "X-Attempts": "1",
                        "Content-Length": str(len(content)),
                    },
                    status_code=200,
                )
            return {
                "cached": True,
                "statusCode": cached.status_code,
                "data": cached.response_json,
                "expiresAt": cached.expires_at.isoformat(),
                "hitCount": cached.hit_count,
            }

        # Call external API with retry on 429
        attempt = 0
        response = None
        while attempt <= (payload.maxRetries or 3):
            try:
                response = requests.request(
                    method,
                    payload.url,
                    headers=payload.headers or {},
                    timeout=30,
                )
                if response.status_code != 429:
                    break
            except Exception:
                if attempt == (payload.maxRetries or 3):
                    break
            if response and response.status_code == 429 and attempt < (payload.maxRetries or 3):
                time.sleep(2 ** attempt)
            attempt += 1

        if response is None:
            raise HTTPException(status_code=502, detail="External request failed")

        data = None
        try:
            data = response.json()
        except Exception:
            data = {"raw": response.text}

        # Cache successful responses
        cached_hit = cached is not None
        if 200 <= response.status_code < 300:
            expires = now + timedelta(seconds=payload.ttlSeconds or 60)
            existing = (
                db.query(ExternalApiCache)
                .filter(
                    ExternalApiCache.url == payload.url,
                    ExternalApiCache.method == method,
                )
                .first()
            )
            if existing:
                existing.response_json = data
                existing.status_code = response.status_code
                existing.cached_at = now
                existing.expires_at = expires
                existing.hit_count = 0
            else:
                entry = ExternalApiCache(
                    id=uuid4(),
                    url=payload.url,
                    method=method,
                    response_json=data,
                    status_code=response.status_code,
                    cached_at=now,
                    expires_at=expires,
                    hit_count=0,
                )
                db.add(entry)
            db.commit()

        if payload.unwrap:
            # When unwrapping, always return 200 with a JSON body so n8n HTTP Request
            # nodes don't fail on upstream 4xx/5xx/204 responses (e.g. rate limits or
            # empty bodies). Workflows inspect the payload and handle errors/missing
            # fields in Code nodes.
            content = json.dumps(data, ensure_ascii=False).encode("utf-8")
            headers = {
                "X-Cache": "MISS",
                "X-Attempts": str(attempt + 1),
                "Content-Length": str(len(content)),
            }
            return Response(
                content=content,
                media_type="application/json",
                headers=headers,
                status_code=200,
            )

        return {
            "cached": cached_hit,
            "statusCode": response.status_code,
            "data": data,
            "attempts": attempt + 1,
        }

    @r.get("/proxy/football/fixtures")
    async def get_football_fixtures(
        date_from: str = Query(..., alias="dateFrom", description="Start date YYYY-MM-DD"),
        date_to: str = Query(..., alias="dateTo", description="End date YYYY-MM-DD"),
    ):
        """Fetch football fixtures with football-data.org as primary and RapidAPI as fallback.

        Returns a normalized match list compatible with the n8n workflow's football parser.
        """
        token = os.environ.get("FOOTBALL_DATA_ORG_TOKEN", "")
        rapidapi_key = os.environ.get("RAPIDAPI_KEY", "")

        primary_matches = []
        primary_source = None
        if token:
            try:
                # football-data.org requires dateTo > dateFrom: a 0-day span
                # (dateFrom == dateTo, as sent by the n8n per-date loop) always
                # returns 0 matches. Extending one day also catches Bogota-evening
                # matches whose utcDate falls on the next UTC day.
                from datetime import datetime as _fdt
                fd_date_to = date_to
                try:
                    fd_date_to = (_fdt.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
                except ValueError:
                    pass
                primary_url = (
                    "https://api.football-data.org/v4/matches"
                    f"?dateFrom={date_from}&dateTo={fd_date_to}"
                )
                resp = requests.get(
                    primary_url,
                    headers={"X-Auth-Token": token},
                    timeout=20,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    primary_matches = _normalize_football_data_org_matches(data.get("matches") or [])
                    primary_source = "football-data.org"
                else:
                    logging.warning(
                        f"[FOOTBALL] football-data.org returned {resp.status_code}: {resp.text[:200]}"
                    )
            except Exception as e:
                logging.warning(f"[FOOTBALL] football-data.org request failed: {e}")

        if primary_matches:
            return {"source": primary_source, "matches": primary_matches}

        # Fallback to RapidAPI
        fallback_matches = []
        try:
            from datetime import datetime as _dt
            start = _dt.strptime(date_from, "%Y-%m-%d")
            end = _dt.strptime(date_to, "%Y-%m-%d")
            current = start
            while current <= end:
                date_str = current.strftime("%Y%m%d")
                url = (
                    "https://free-api-live-football-data.p.rapidapi.com/football-get-matches-by-date"
                    f"?date={date_str}"
                )
                resp = requests.get(
                    url,
                    headers={
                        "Content-Type": "application/json",
                        "x-rapidapi-host": "free-api-live-football-data.p.rapidapi.com",
                        "x-rapidapi-key": rapidapi_key,
                    },
                    timeout=30,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    day_matches = data.get("response", {}).get("matches") or []
                    fallback_matches.extend(day_matches)
                else:
                    logging.warning(
                        f"[FOOTBALL] RapidAPI fallback returned {resp.status_code} for {date_str}: {resp.text[:200]}"
                    )
                current += timedelta(days=1)
        except Exception as e:
            logging.warning(f"[FOOTBALL] RapidAPI fallback request failed: {e}")

        return {"source": "rapidapi", "matches": fallback_matches}


    def _normalize_football_data_org_matches(raw_matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert football-data.org match objects to the RapidAPI-like schema used by n8n."""
        normalized = []
        for m in raw_matches:
            try:
                match_id = m.get("id")
                competition = m.get("competition") or {}
                home_team = m.get("homeTeam") or {}
                away_team = m.get("awayTeam") or {}
                score = m.get("score") or {}
                full_time = score.get("fullTime") or {}
                status = (m.get("status") or "").upper()
                utc_date = m.get("utcDate")

                status_obj = {"utcTime": utc_date}
                if status == "FINISHED":
                    status_obj["finished"] = True
                elif status in ("IN_PLAY", "LIVE", "PAUSED"):
                    status_obj["started"] = True
                elif status in ("CANCELLED", "POSTPONED", "ABANDONED", "SUSPENDED"):
                    status_obj["cancelled"] = True

                normalized.append({
                    "id": match_id,
                    "leagueId": competition.get("id"),
                    "home": {
                        "name": home_team.get("name") or home_team.get("shortName"),
                        "longName": home_team.get("name"),
                    },
                    "away": {
                        "name": away_team.get("name") or away_team.get("shortName"),
                        "longName": away_team.get("name"),
                    },
                    "status": status_obj,
                    "homeScore": full_time.get("home"),
                    "awayScore": full_time.get("away"),
                })
            except Exception:
                continue
        return normalized

    def _parse_date(value: Optional[str]) -> Optional[date]:
        if not value or not value.strip():
            return None
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            try:
                return datetime.fromisoformat(value.strip()).date()
            except ValueError:
                return None

    @r.post("/features/build")
    async def build_features(
        request_data: Optional[Dict[str, Any]] = None,
        sport: Optional[str] = Query(None, description="Sport code (football, tennis)"),
        from_str: Optional[str] = Query(None, alias="from"),
        to_str: Optional[str] = Query(None, alias="to"),
        db: Session = Depends(get_db),
    ):
        """Build per-match, per-competitor feature vectors and store them.

        Accepts either a JSON body with `match_ids` (internal UUIDs) or
        `external_match_ids`, or a date range/sport filter. Used by the
        prediction pipeline before generating predictions. Empty date params
        (n8n sends from=&to= when unset) are tolerated; without explicit ids
        or dates it defaults to today (Bogotá), mirroring /matches/by-date.
        """
        request_data = request_data or {}
        match_ids = request_data.get("match_ids") or request_data.get("matchIds")
        external_ids = request_data.get("external_match_ids") or request_data.get("externalMatchIds")

        if external_ids:
            matches = db.query(Match).filter(Match.external_id.in_(external_ids)).all()
            match_ids = [str(m.id) for m in matches]
            if not match_ids:
                return {
                    "version": FeatureService.FEATURE_VERSION,
                    "matches_processed": 0,
                    "features_created": 0,
                    "features_updated": 0,
                    "errors": [],
                }

        d_from = _parse_date(from_str)
        d_to = _parse_date(to_str)
        if not d_from and not d_to and not match_ids and not external_ids:
            d_from = today_bogota()
        if not d_from:
            d_from = d_to
        if not d_to:
            d_to = d_from
        from_date = datetime.combine(d_from, datetime.min.time(), tzinfo=BOGOTA_TZ) if d_from else None
        to_date = datetime.combine(d_to, datetime.max.time(), tzinfo=BOGOTA_TZ) if d_to else None
        sport = sport.strip() if sport else None

        service = FeatureService(db)
        result = service.build_features_for_matches(
            match_ids=match_ids,
            sport_code=sport,
            from_date=from_date,
            to_date=to_date,
        )
        return result

    return r
