"""CDC worker that migrates JSON files from filesystem to PostgreSQL.

This worker polls the storage directories for new files, inserts their contents
into the database, and optionally deletes the source files to free disk space.
"""
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.application.services import DataService
from src.domain.models import (
    Competitor,
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
from src.infrastructure.database import get_db_context


STORAGE_PATH = os.getenv("STORAGE_PATH", "/storage")
POLL_INTERVAL = int(os.getenv("WORKER_POLL_INTERVAL", "10"))
DELETE_AFTER_MIGRATE = os.getenv("WORKER_DELETE_AFTER_MIGRATE", "true").lower() == "true"
MIN_FILE_AGE_SECONDS = int(os.getenv("WORKER_MIN_FILE_AGE_SECONDS", "3600"))

SUPPORTED_TYPES = ["matches", "predictions", "results"]


def _file_age_seconds(path: Path) -> float:
    stat = path.stat()
    return datetime.now(timezone.utc).timestamp() - stat.st_mtime


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_already_processed(db: Session, filename: str, file_hash: str) -> bool:
    existing = db.query(ProcessedFile).filter(ProcessedFile.filename == filename).first()
    if existing and existing.file_hash == file_hash:
        return True
    return False


def _normalize_status(status: Optional[str]) -> str:
    if not status:
        return "SCHEDULED"
    status_upper = status.upper()
    if any(k in status_upper for k in ("LIVE", "1H", "2H", "HT", "HALF", "IN PROGRESS")):
        return "LIVE"
    if any(k in status_upper for k in ("FINISHED", "FT", "FULL", "ENDED", "POSTPONED", "CANCELLED", "ABANDONED")):
        return "FINISHED" if "POSTPONED" not in status_upper and "CANCELLED" not in status_upper and "ABANDONED" not in status_upper else status_upper
    # Score strings like "2 - 1" mean finished
    if "-" in status:
        return "FINISHED"
    return "SCHEDULED"


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except Exception:
        return datetime.now(timezone.utc)


def _ensure_sport(db: Session, code: str, name: str) -> Sport:
    sport = db.query(Sport).filter(Sport.code == code).first()
    if not sport:
        sport = Sport(code=code, name=name)
        db.add(sport)
        db.commit()
        db.refresh(sport)
    return sport


def _ensure_league(db: Session, sport_id: Any, name: str, external_id: Optional[str] = None) -> League:
    league = db.query(League).filter(League.sport_id == sport_id, League.name == name).first()
    if not league:
        league = League(sport_id=sport_id, name=name, external_id=external_id)
        db.add(league)
        db.commit()
        db.refresh(league)
    return league


def _ensure_competitor(db: Session, sport_id: Any, name: str, competitor_type: str, external_id: Optional[str] = None) -> Competitor:
    competitor = (
        db.query(Competitor)
        .filter(
            Competitor.sport_id == sport_id,
            Competitor.name.ilike(name),
            Competitor.type == competitor_type,
        )
        .first()
    )
    if not competitor:
        competitor = Competitor(
            sport_id=sport_id,
            name=name,
            type=competitor_type,
            external_id=external_id,
        )
        db.add(competitor)
        db.commit()
        db.refresh(competitor)
    return competitor


def _insert_match(
    db: Session,
    sport_code: str,
    sport_name: str,
    competitor_type: str,
    raw: Dict[str, Any],
    side_mapping: Dict[str, str],
    generated_at: datetime,
    source_api: Optional[str] = None,
) -> bool:
    try:
        sport = _ensure_sport(db, sport_code, sport_name)
        league_name = raw.get("league") or raw.get("tournament") or "Unknown"
        league = _ensure_league(db, sport.id, league_name)

        match_external_id = raw.get("matchId") or (str(raw.get("eventId")) if raw.get("eventId") else None)
        if not match_external_id:
            return False

        match_date = _parse_iso_datetime(raw.get("eventDate")) or generated_at
        if raw.get("eventTime"):
            try:
                hour, minute = raw["eventTime"].split(":")[:2]
                match_date = match_date.replace(hour=int(hour), minute=int(minute))
            except Exception:
                pass

        match = (
            db.query(Match)
            .filter(Match.external_id == match_external_id, Match.sport_id == sport.id)
            .first()
        )
        if not match:
            match = Match(
                sport_id=sport.id,
                league_id=league.id,
                external_id=match_external_id,
                source_api=source_api or "rapidapi",
                match_date=match_date,
                status=_normalize_status(raw.get("status")),
                extra_data={
                    "surface": raw.get("surface"),
                    "h2h": raw.get("h2h"),
                },
                created_at=generated_at,
            )
            db.add(match)
            db.commit()
            db.refresh(match)
        else:
            match.match_date = match_date
            match.status = _normalize_status(raw.get("status")) if raw.get("status") else match.status
            match.extra_data = {
                **(match.extra_data or {}),
                "surface": raw.get("surface"),
                "h2h": raw.get("h2h"),
            }
            db.commit()
            db.refresh(match)

        for side_key, side_name in side_mapping.items():
            name = raw.get(side_key)
            if not name:
                continue
            competitor = _ensure_competitor(db, sport.id, name, competitor_type)

            metadata = {}
            if sport_code == "football":
                prefix = "home" if side_key == "homeTeam" else "away"
                metadata = {
                    "expected_goals": raw.get(f"{prefix}Xg") or raw.get(f"{prefix}_xg"),
                    "corners_avg": raw.get(f"{prefix}Corners") or raw.get(f"{prefix}_corners"),
                }
                ranking_key = f"{prefix}Position"
                form_key = f"{prefix}Form"
            else:
                prefix = "player1" if side_key == "player1" else "player2"
                metadata = {
                    "aces_avg": raw.get(f"{prefix}AcesAvg") or raw.get(f"aces_avg_{prefix}"),
                }
                ranking_key = f"ranking{prefix.capitalize()}"
                form_key = f"form{prefix.capitalize()}"

            link = (
                db.query(MatchCompetitor)
                .filter(MatchCompetitor.match_id == match.id, MatchCompetitor.side == side_name)
                .first()
            )
            if not link:
                link = MatchCompetitor(
                    match_id=match.id,
                    competitor_id=competitor.id,
                    side=side_name,
                    pre_match_ranking=raw.get(ranking_key),
                    pre_match_form=raw.get(form_key),
                    extra_data=metadata,
                )
                db.add(link)
            else:
                link.pre_match_ranking = raw.get(ranking_key, link.pre_match_ranking)
                link.pre_match_form = raw.get(form_key, link.pre_match_form)
                link.extra_data = {**(link.extra_data or {}), **metadata}
            db.commit()

        if "homeScore" in raw and "awayScore" in raw:
            score = (
                db.query(MatchScore)
                .filter(MatchScore.match_id == match.id, MatchScore.period == "FULL_TIME")
                .first()
            )
            if not score:
                score = MatchScore(
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

        return True
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Failed to insert match: {e}")
        return False


def _migrate_matches(db: Session, data: Dict[str, Any]) -> int:
    generated_at = _parse_iso_datetime(data.get("generatedAt")) or datetime.now(timezone.utc)
    source_api = data.get("source", "live_api")
    count = 0

    for raw in data.get("football", []):
        if _insert_match(
            db,
            sport_code="football",
            sport_name="Football",
            competitor_type="team",
            raw=raw,
            side_mapping={"homeTeam": "home", "awayTeam": "away"},
            generated_at=generated_at,
            source_api=source_api,
        ):
            count += 1

    for raw in data.get("tennis", []):
        if _insert_match(
            db,
            sport_code="tennis",
            sport_name="Tennis",
            competitor_type="player",
            raw=raw,
            side_mapping={"player1": "player1", "player2": "player2"},
            generated_at=generated_at,
            source_api=source_api,
        ):
            count += 1

    return count


def _migrate_predictions(db: Session, data: Dict[str, Any]) -> int:
    generated_at = _parse_iso_datetime(data.get("generatedAt")) or datetime.now(timezone.utc)
    count = 0

    model = db.query(PredictionModel).filter(PredictionModel.name == "OpenAI Ensemble").first()
    if not model:
        model = PredictionModel(name="OpenAI Ensemble", version="1.0")
        db.add(model)
        db.commit()
        db.refresh(model)

    for raw in data.get("predictions", []):
        try:
            match_id_str = raw.get("matchId")
            if not match_id_str:
                continue

            match = db.query(Match).filter(Match.external_id == str(match_id_str)).first()
            if not match:
                print(f"[WARN] Match not found for prediction: {match_id_str}")
                continue

            prediction_id = raw.get("predictionId")
            prediction = db.query(Prediction).filter(Prediction.id == prediction_id).first() if prediction_id else None
            if not prediction:
                prediction = Prediction(
                    id=prediction_id,
                    match_id=match.id,
                    model_id=model.id,
                    market=raw.get("market", "Unknown"),
                    predicted_outcome=raw.get("prediction", ""),
                    confidence=raw.get("confidence", 0),
                    reasoning=raw.get("reasoning", ""),
                    natural_language_reasoning=raw.get("naturalLanguageReasoning", ""),
                    probabilities=raw.get("probabilities", {}),
                    model_contributions=raw.get("modelContributions", {}),
                    reasoning_data=raw.get("reasoningData", {}),
                    status=raw.get("status", "PENDING"),
                    created_at=generated_at,
                )
                db.add(prediction)
            else:
                prediction.market = raw.get("market", prediction.market)
                prediction.predicted_outcome = raw.get("prediction", prediction.predicted_outcome)
                prediction.confidence = raw.get("confidence", prediction.confidence)
                prediction.reasoning = raw.get("reasoning", prediction.reasoning)
                prediction.natural_language_reasoning = raw.get("naturalLanguageReasoning", prediction.natural_language_reasoning)
                prediction.probabilities = raw.get("probabilities", prediction.probabilities)
                prediction.model_contributions = raw.get("modelContributions", prediction.model_contributions)
                prediction.reasoning_data = raw.get("reasoningData", prediction.reasoning_data)
                prediction.status = raw.get("status", prediction.status)

            db.commit()
            count += 1
        except Exception as e:
            db.rollback()
            print(f"[ERROR] Failed to insert prediction: {e}")

    return count


def _migrate_results(db: Session, data: Dict[str, Any]) -> int:
    generated_at = _parse_iso_datetime(data.get("generatedAt")) or datetime.now(timezone.utc)
    count = 0

    for raw in data.get("results", []):
        try:
            prediction_id = raw.get("predictionId")
            if not prediction_id:
                continue

            prediction = db.query(Prediction).filter(Prediction.id == prediction_id).first()
            if not prediction:
                print(f"[WARN] Prediction not found for result: {prediction_id}")
                continue

            result = (
                db.query(PredictionResult)
                .filter(PredictionResult.prediction_id == prediction.id)
                .first()
            )
            if not result:
                result = PredictionResult(
                    prediction_id=prediction.id,
                    actual_outcome=raw.get("actualResult"),
                    is_successful=raw.get("success"),
                    match_score_snapshot=raw.get("matchScore") or raw.get("match_score_snapshot"),
                    validation_notes=raw.get("validationReason") or raw.get("validation_reason"),
                    validated_at=generated_at,
                )
                db.add(result)
            else:
                result.actual_outcome = raw.get("actualResult", result.actual_outcome)
                result.is_successful = raw.get("success", result.is_successful)
                result.match_score_snapshot = raw.get("matchScore") or raw.get("match_score_snapshot", result.match_score_snapshot)
                result.validation_notes = raw.get("validationReason") or raw.get("validation_reason", result.validation_notes)
                result.validated_at = generated_at

            if result.is_successful is True:
                prediction.status = "VALIDATED"
            elif result.is_successful is False:
                prediction.status = "FAILED"

            db.commit()
            count += 1
        except Exception as e:
            db.rollback()
            print(f"[ERROR] Failed to insert result: {e}")

    return count


def _process_file(db: Session, file_path: Path, file_type: str) -> int:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to parse {file_path}: {e}")
        return 0

    if file_type == "matches":
        count = _migrate_matches(db, data)
    elif file_type == "predictions":
        count = _migrate_predictions(db, data)
    elif file_type == "results":
        count = _migrate_results(db, data)
    else:
        return 0

    return count


def run_once() -> Dict[str, int]:
    stats = {"processed": 0, "records": 0, "deleted": 0, "errors": 0}

    with get_db_context() as db:
        for file_type in SUPPORTED_TYPES:
            directory = Path(STORAGE_PATH) / file_type
            if not directory.exists():
                continue

            files = sorted(directory.glob(f"{file_type}_*.json"))
            for file_path in files:
                try:
                    file_hash = _file_hash(file_path)
                    if _is_already_processed(db, file_path.name, file_hash):
                        if DELETE_AFTER_MIGRATE and _file_age_seconds(file_path) >= MIN_FILE_AGE_SECONDS:
                            file_path.unlink()
                            stats["deleted"] += 1
                        continue

                    records = _process_file(db, file_path, file_type)

                    processed = ProcessedFile(
                        filename=file_path.name,
                        file_hash=file_hash,
                        file_type=file_type,
                        records_inserted=records,
                        processed_at=datetime.now(timezone.utc),
                    )
                    db.add(processed)
                    db.commit()

                    stats["processed"] += 1
                    stats["records"] += records

                    if DELETE_AFTER_MIGRATE and _file_age_seconds(file_path) >= MIN_FILE_AGE_SECONDS:
                        file_path.unlink()
                        stats["deleted"] += 1
                except Exception as e:
                    db.rollback()
                    stats["errors"] += 1
                    print(f"[ERROR] Failed to process {file_path}: {e}")

    return stats


def main() -> None:
    print("=" * 60)
    print("BrainBets Migration Worker")
    print(f"Storage: {STORAGE_PATH}")
    print(f"Poll interval: {POLL_INTERVAL}s")
    print(f"Delete after migrate: {DELETE_AFTER_MIGRATE}")
    print("=" * 60)

    while True:
        try:
            stats = run_once()
            if stats["processed"] > 0 or stats["errors"] > 0:
                print(f"[{datetime.now(timezone.utc).isoformat()}] {stats}")
        except Exception as e:
            print(f"[ERROR] Worker loop failed: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
