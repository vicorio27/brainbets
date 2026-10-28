"""Prediction validation service.

Validates pending predictions against match results stored in the database.
For finished matches with scores, it determines the actual outcome and
whether each prediction was successful.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from src.domain.models import Match, MatchScore, Prediction, PredictionResult, Sport
from src.timezone import today_start_bogota, yesterday_start_bogota, tomorrow_start_bogota, now_bogota


def _normalize_team_name(name: str) -> str:
    return " ".join(name.lower().split())


def _match_winner(match: Match, score: MatchScore) -> Optional[str]:
    """Return the winner team name for a football match, or 'Draw'."""
    competitors = {c.side: c for c in match.competitors}
    home = competitors.get("home")
    away = competitors.get("away")
    if not home or not away or score.home_score is None or score.away_score is None:
        return None

    if score.home_score > score.away_score:
        return home.competitor.name
    elif score.away_score > score.home_score:
        return away.competitor.name
    else:
        return "Draw"


def _tennis_winner(match: Match, score: MatchScore) -> Optional[str]:
    """Return the winner player name for a tennis match."""
    competitors = {c.side: c for c in match.competitors}
    p1 = competitors.get("player1")
    p2 = competitors.get("player2")
    if not p1 or not p2 or score.home_score is None or score.away_score is None:
        return None

    if score.home_score > score.away_score:
        return p1.competitor.name
    elif score.away_score > score.home_score:
        return p2.competitor.name
    return None


def _over_under_result(total: float, line: float) -> str:
    return "Over" if total > line else "Under"


def _btts_result(home_score: int, away_score: int) -> str:
    return "Yes" if home_score > 0 and away_score > 0 else "No"


def _validate_football(prediction: Prediction, match: Match, score: MatchScore) -> Dict[str, Any]:
    home_score = score.home_score or 0
    away_score = score.away_score or 0
    total = home_score + away_score
    market = prediction.market.lower()
    predicted = prediction.predicted_outcome
    actual = None
    success = None
    notes = f"Final score: {home_score}-{away_score}"

    if "winner" in market or "match winner" in market:
        actual = _match_winner(match, score)
        if actual and predicted:
            success = _normalize_team_name(actual) == _normalize_team_name(predicted)
    elif "over/under" in market or "over under" in market:
        # Extract line from market string, e.g. "Over/Under 2.5 Goals"
        import re
        line_match = re.search(r"(\d+\.?\d*)", prediction.market)
        line = float(line_match.group(1)) if line_match else 2.5
        actual_result = _over_under_result(total, line)
        actual = f"{actual_result} {line}"
        success = actual == predicted
    elif "both teams to score" in market or "btts" in market:
        actual = _btts_result(home_score, away_score)
        success = actual.lower() == predicted.lower()
    else:
        notes = f"Unsupported market: {prediction.market}. Score: {home_score}-{away_score}"

    return {
        "actual_outcome": actual,
        "success": success,
        "notes": notes,
    }


def _validate_tennis(prediction: Prediction, match: Match, score: MatchScore) -> Dict[str, Any]:
    home_score = score.home_score or 0
    away_score = score.away_score or 0
    market = prediction.market.lower()
    predicted = prediction.predicted_outcome
    actual = None
    success = None
    notes = f"Final score (sets): {home_score}-{away_score}"

    if "set 1 winner" in market:
        stats = (match.extra_data or {}).get("score_stats") or {}
        set_rows = stats.get("sets") or []
        competitors = {c.side: c for c in match.competitors}
        mc1 = competitors.get("player1")
        mc2 = competitors.get("player2")
        first = set_rows[0] if set_rows else None
        p1_games = p2_games = None
        if first is not None:
            try:
                p1_games = int(first.get("p1"))
                p2_games = int(first.get("p2"))
            except (TypeError, ValueError):
                p1_games = p2_games = None

        if p1_games is not None and p2_games is not None and p1_games != p2_games and mc1 and mc2:
            # Per-set data available: use the actual first set.
            actual = mc1.competitor.name if p1_games > p2_games else mc2.competitor.name
            success = _normalize_team_name(actual) == _normalize_team_name(predicted or "")
            notes = f"Set 1: {p1_games}-{p2_games} (games). Winner: {actual}. Prediction: {predicted}."
        elif (
            mc1 and mc2
            and home_score is not None and away_score is not None
            and min(home_score, away_score) == 0
            and max(home_score, away_score) > 0
        ):
            # No per-set breakdown, but the match was a straight-sets sweep, so
            # whoever won the match necessarily won the first set.
            actual = mc1.competitor.name if home_score > away_score else mc2.competitor.name
            success = _normalize_team_name(actual) == _normalize_team_name(predicted or "")
            notes = (
                f"Sin desglose por set; el partido fue barrida {home_score}-{away_score}, "
                f"así que el Set 1 lo ganó {actual}. Prediction: {predicted}."
            )
        else:
            # Genuinely unknown: leave pending rather than scoring it as a loss.
            actual = "N/A"
            success = None
            notes = "Set-level score data not available; Set 1 Winner left pending."
    elif "winner" in market or "match winner" in market:
        actual = _tennis_winner(match, score)
        if actual and predicted:
            success = _normalize_team_name(actual) == _normalize_team_name(predicted)
    elif "total aces" in market:
        stats = (match.extra_data or {}).get("score_stats") or {}
        home_aces = stats.get("homeAces")
        away_aces = stats.get("awayAces")
        if home_aces is None or away_aces is None:
            notes = "Aces data not available from match statistics"
            actual = "N/A"
            success = False
        else:
            total_aces = int(home_aces) + int(away_aces)
            actual = f"{total_aces} aces"
            if "over" in predicted.lower():
                success = total_aces > 15.5
            elif "under" in predicted.lower():
                success = total_aces <= 15.5
            else:
                success = False
            notes = f"Total aces: {total_aces} (home {home_aces}, away {away_aces}). Prediction: {predicted}."
    elif "total sets" in market:
        total_sets = home_score + away_score
        # Line comes from the predicted outcome ("Over 2.5" for best-of-3,
        # "Over 3.5" for Grand Slam best-of-5); default 2.5 for legacy rows.
        line_match = re.search(r"(\d+(?:\.\d+)?)", predicted or "")
        line = float(line_match.group(1)) if line_match else 2.5
        actual = f"{total_sets} sets"
        if "over" in predicted.lower():
            success = total_sets > line
        elif "under" in predicted.lower():
            success = total_sets <= line
        notes = f"Total sets played: {total_sets} (línea {line}). Prediction: {predicted}."
    elif "exact set score" in market:
        winner = _tennis_winner(match, score)
        if winner:
            # Picks read from the winner's side ("Struff 2-0"), so an away win
            # must not be written home-first ("Struff 0-2").
            actual = f"{winner} {max(home_score, away_score)}-{min(home_score, away_score)}"
            success = _normalize_team_name(actual) == _normalize_team_name(predicted or "")
            notes = f"Exact set score: {actual}. Prediction: {predicted}."
        else:
            notes = f"Could not determine winner. Score: {home_score}-{away_score}"
    else:
        notes = f"Unsupported market: {prediction.market}. Score: {home_score}-{away_score}"

    return {
        "actual_outcome": actual,
        "success": success,
        "notes": notes,
    }


# A prediction must not sit in PENDING forever. After this long without a
# usable result it is closed as CANCELLED, with the reason kept in its result.
STALE_AFTER = timedelta(days=3)
OPEN_STATUSES = ("PENDING", "LOW_CONFIDENCE")


def stale_reason(match_status: Optional[str], match_date: Optional[datetime], created_at: Optional[datetime],
                 now: datetime) -> Optional[str]:
    """Why an open prediction can never be settled, or None while it still can."""
    if match_status == "CANCELLED":
        return "Partido anulado (retiro, walkover o cancelación): la apuesta no cuenta."
    if not match_date:
        return None
    old = match_date < now - STALE_AFTER
    if created_at and created_at >= match_date and old:
        return "Predicción creada cuando el partido ya había empezado: no se podía apostar."
    if match_status != "FINISHED" and old:
        return "El resultado del partido nunca llegó."
    return None


def _close(db: Session, pred: Prediction, reason: str, now: datetime) -> None:
    pred.status = "CANCELLED"
    result = db.query(PredictionResult).filter(PredictionResult.prediction_id == pred.id).first()
    if not result:
        result = PredictionResult(id=uuid4(), prediction_id=pred.id)
        db.add(result)
    result.is_successful = None
    result.validation_notes = reason
    result.validated_at = now


def close_stale_predictions(db: Session, sport: Optional[str] = None) -> Dict[str, int]:
    """Give a final state to open predictions that can never be validated."""
    now = datetime.now(timezone.utc)
    query = db.query(Prediction).join(Prediction.match).filter(Prediction.status.in_(OPEN_STATUSES))
    if sport:
        query = query.join(Match.sport).filter(Sport.code == sport.lower())
    closed: Dict[str, int] = {}
    for pred in query.all():
        match = pred.match
        reason = stale_reason(match.status, match.match_date, pred.created_at, now) if match else None
        if reason:
            _close(db, pred, reason, now)
            closed[reason] = closed.get(reason, 0) + 1
    db.commit()
    return closed


def validate_pending_predictions(db: Session, sport: Optional[str] = None) -> Dict[str, Any]:
    """Validate pending predictions against DB match results.

    Validated: every open prediction whose match is today or yesterday, plus
    any whose match is already FINISHED whatever its date (a result that
    arrives late must still settle its predictions). Before that, predictions
    that can never be settled are closed as CANCELLED (`close_stale_predictions`).

    Args:
        db: SQLAlchemy session.
        sport: Optional sport code to filter predictions (football, tennis).

    Returns a dict with results list and summary counts.
    """
    closed = close_stale_predictions(db, sport)
    now = now_bogota()
    today_start = today_start_bogota()
    yesterday_start = yesterday_start_bogota()
    tomorrow_start = today_start + timedelta(days=1)

    # Base query: all pending or low-confidence predictions for the sport (or all sports)
    base_query = (
        db.query(Prediction)
        .join(Prediction.match)
        .filter(Prediction.status.in_(["PENDING", "LOW_CONFIDENCE"]))
    )
    if sport:
        base_query = base_query.join(Match.sport).filter(Sport.code == sport.lower())

    total_pending = base_query.count()

    # Today's and yesterday's matches, plus anything already finished.
    query = base_query.filter(
        or_(
            and_(Match.match_date >= yesterday_start, Match.match_date < tomorrow_start),
            Match.status == "FINISHED",
        )
    )
    predictions = query.all()

    results = []
    summary = {
        "total": len(predictions),
        "matched": 0,
        "validated": 0,
        "successful": 0,
        "failed": 0,
        "pending": 0,
        "skipped": total_pending - len(predictions),
        "closed": sum(closed.values()),
        "closedByReason": closed,
        "dateWindow": {
            "from": yesterday_start.isoformat(),
            "to": tomorrow_start.isoformat(),
        },
        "bySport": {},
        "byMarket": {},
        "byMatch": {},
    }

    now = datetime.now(timezone.utc)

    for pred in predictions:
        match = pred.match
        if not match:
            summary["pending"] += 1
            continue

        score = (
            db.query(MatchScore)
            .filter(MatchScore.match_id == match.id, MatchScore.period == "FULL_TIME")
            .first()
        )

        result_data = {
            "predictionId": str(pred.id),
            "actualResult": None,
            "success": None,
            "validationReason": "",
            "matchScore": None,
        }

        sport_code = match.sport.code if match.sport else ""
        sport_name = match.sport.name if match.sport else "Unknown"
        sport_bucket = summary["bySport"].setdefault(
            sport_name,
            {"total": 0, "matched": 0, "validated": 0, "successful": 0, "failed": 0, "pending": 0},
        )
        sport_bucket["total"] += 1

        market_bucket = summary["byMarket"].setdefault(
            pred.market,
            {"total": 0, "matched": 0, "validated": 0, "successful": 0, "failed": 0, "pending": 0},
        )
        market_bucket["total"] += 1

        if match.status != "FINISHED" or not score:
            result_data["validationReason"] = f"Match status: {match.status}. No final score available."
            summary["pending"] += 1
            sport_bucket["pending"] += 1
            market_bucket["pending"] += 1
            results.append(result_data)
            continue

        summary["matched"] += 1
        sport_bucket["matched"] += 1
        market_bucket["matched"] += 1
        result_data["matchScore"] = f"{score.home_score}-{score.away_score}"

        competitors = {c.side: c for c in match.competitors}
        home_team = competitors.get("home", competitors.get("player1"))
        away_team = competitors.get("away", competitors.get("player2"))
        home_name = home_team.competitor.name if home_team and home_team.competitor else ""
        away_name = away_team.competitor.name if away_team and away_team.competitor else ""

        match_key = f"{match.external_id or str(match.id)}|{home_name} vs {away_name}"
        match_bucket = summary["byMatch"].setdefault(
            match_key,
            {
                "matchId": match.external_id or str(match.id),
                "homeTeam": home_name,
                "awayTeam": away_name,
                "total": 0,
                "successful": 0,
                "failed": 0,
            },
        )
        match_bucket["total"] += 1

        if sport_code == "football":
            validation = _validate_football(pred, match, score)
        elif sport_code == "tennis":
            validation = _validate_tennis(pred, match, score)
        else:
            validation = {
                "actual_outcome": None,
                "success": None,
                "notes": f"Unsupported sport: {sport_code}",
            }

        result_data["actualResult"] = validation["actual_outcome"]
        result_data["success"] = validation["success"]
        result_data["validationReason"] = validation["notes"]

        # Upsert PredictionResult
        existing = (
            db.query(PredictionResult)
            .filter(PredictionResult.prediction_id == pred.id)
            .first()
        )
        if not existing:
            existing = PredictionResult(
                id=uuid4(),
                prediction_id=pred.id,
            )
            db.add(existing)

        existing.actual_outcome = validation["actual_outcome"]
        existing.is_successful = validation["success"]
        existing.match_score_snapshot = result_data["matchScore"]
        existing.validation_notes = validation["notes"]
        existing.validated_at = now

        # Update prediction status
        if validation["success"] is True:
            pred.status = "VALIDATED"
            summary["successful"] += 1
            summary["validated"] += 1
            sport_bucket["successful"] += 1
            sport_bucket["validated"] += 1
            market_bucket["successful"] += 1
            market_bucket["validated"] += 1
            match_bucket["successful"] += 1
        elif validation["success"] is False:
            pred.status = "FAILED"
            summary["failed"] += 1
            summary["validated"] += 1
            sport_bucket["failed"] += 1
            sport_bucket["validated"] += 1
            market_bucket["failed"] += 1
            market_bucket["validated"] += 1
            match_bucket["failed"] += 1
        elif match.match_date and match.match_date < now - STALE_AFTER:
            # Finished long ago and still not decidable: the data needed never came.
            _close(db, pred, "El partido terminó pero faltan los datos para validar este mercado.", now)
            summary["closed"] += 1
        else:
            summary["pending"] += 1
            sport_bucket["pending"] += 1
            market_bucket["pending"] += 1

        results.append(result_data)

    db.commit()

    valid_count = summary["successful"] + summary["failed"]
    summary["accuracy"] = round(summary["successful"] / valid_count * 100, 2) if valid_count > 0 else 0.0

    return {
        "generatedAt": now.isoformat(),
        "results": results,
        "summary": summary,
    }
