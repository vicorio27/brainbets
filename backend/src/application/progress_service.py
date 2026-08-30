"""Live prediction progress and fulfillment service.

Computes how likely each pending prediction is to succeed given the current
match state (score, minute, set/game/point). Stores snapshots in
`prediction_progress` so the dashboard and Telegram can show evolution.
"""
import math
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.domain.models import Match, Prediction, PredictionProgress


# ---------------------------------------------------------------------------
# Poisson helpers
# ---------------------------------------------------------------------------
def _poisson_pmf(k: int, lam: float) -> float:
    """Poisson probability mass function."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def _poisson_cdf_le(k_max: int, lam: float) -> float:
    """P(X <= k_max) for X ~ Poisson(lam)."""
    return sum(_poisson_pmf(k, lam) for k in range(0, k_max + 1))


def _match_state_from_match(match: Match) -> Dict[str, Any]:
    """Extract expected goals/ratings from match extra_data if available."""
    extra = match.extra_data or {}
    home_xg = extra.get("expectedHomeGoals") or extra.get("homeAttack") or 0.0
    away_xg = extra.get("expectedAwayGoals") or extra.get("awayDefense") or 0.0
    return {"home_xg": home_xg, "away_xg": away_xg}


# ---------------------------------------------------------------------------
# Football fulfillment
# ---------------------------------------------------------------------------
def _football_lambdas(match: Match, minute: int, home_score: int, away_score: int) -> tuple:
    """Return remaining expected goals for home and away.

    Uses stored xG when available; otherwise falls back to conservative
    defaults based on current score (lower scoring when few goals so far).
    """
    state = _match_state_from_match(match)
    home_xg = float(state.get("home_xg") or 0)
    away_xg = float(state.get("away_xg") or 0)

    # Default total xG: scale with observed first-half goals if available.
    if home_xg > 0 and away_xg > 0:
        total_xg = home_xg + away_xg
        home_share = home_xg / total_xg
    else:
        total_xg = max(2.4, home_score + away_score + 1.4)
        home_share = 0.55

    remaining_minutes = max(1, 90 - minute)
    share_remaining = remaining_minutes / 90.0
    lambda_home = total_xg * home_share * share_remaining
    lambda_away = total_xg * (1 - home_share) * share_remaining
    return lambda_home, lambda_away


def _football_match_winner_probabilities(
    home_score: int, away_score: int, lambda_home: float, lambda_away: float
) -> Dict[str, float]:
    """Return {home, draw, away} win probabilities from current score."""
    p_home = p_draw = p_away = 0.0
    max_goals = 8
    for gh in range(0, max_goals + 1):
        p_gh = _poisson_pmf(gh, lambda_home)
        for ga in range(0, max_goals + 1):
            p_ga = _poisson_pmf(ga, lambda_away)
            final_home = home_score + gh
            final_away = away_score + ga
            joint = p_gh * p_ga
            if final_home > final_away:
                p_home += joint
            elif final_home == final_away:
                p_draw += joint
            else:
                p_away += joint
    return {"home": p_home, "draw": p_draw, "away": p_away}


def _normalize_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Convert incoming camelCase snapshot keys to snake_case used by the service."""
    return {
        "home_score": int(snapshot.get("homeScore") or snapshot.get("home_score") or 0),
        "away_score": int(snapshot.get("awayScore") or snapshot.get("away_score") or 0),
        "minute": int(snapshot.get("minute") or 0),
        "period_label": snapshot.get("periodLabel") or snapshot.get("period_label") or "",
        "home_sets": int(snapshot.get("homeSets") or snapshot.get("home_sets") or 0),
        "away_sets": int(snapshot.get("awaySets") or snapshot.get("away_sets") or 0),
        "home_games_current": int(snapshot.get("homeGamesCurrent") or snapshot.get("home_games_current") or 0),
        "away_games_current": int(snapshot.get("awayGamesCurrent") or snapshot.get("away_games_current") or 0),
        "home_point": snapshot.get("homePoint") or snapshot.get("home_point") or "0",
        "away_point": snapshot.get("awayPoint") or snapshot.get("away_point") or "0",
        "best_of": int(snapshot.get("bestOf") or snapshot.get("best_of") or 3),
    }


def _football_fulfillment(prediction: Prediction, snapshot: Dict[str, Any]) -> float:
    norm = _normalize_snapshot(snapshot)
    market = prediction.market.lower()
    predicted = prediction.predicted_outcome
    home_score = norm["home_score"]
    away_score = norm["away_score"]
    minute = min(90, norm["minute"])
    lambda_home, lambda_away = _football_lambdas(
        prediction.match, minute, home_score, away_score
    )

    if "winner" in market or "match winner" in market:
        probs = _football_match_winner_probabilities(
            home_score, away_score, lambda_home, lambda_away
        )
        norm_predicted = predicted.strip().lower()
        if norm_predicted == "draw":
            return round(probs["draw"] * 100, 2)
        # Compare predicted team name against home/away team names.
        competitors = {c.side: c for c in prediction.match.competitors}
        home_name = (
            competitors.get("home").competitor.name
            if competitors.get("home")
            else ""
        )
        away_name = (
            competitors.get("away").competitor.name
            if competitors.get("away")
            else ""
        )
        if home_name and norm_predicted == home_name.strip().lower():
            return round(probs["home"] * 100, 2)
        if away_name and norm_predicted == away_name.strip().lower():
            return round(probs["away"] * 100, 2)
        # Fallback: if predicted starts with home/away label.
        if norm_predicted.startswith("home"):
            return round(probs["home"] * 100, 2)
        if norm_predicted.startswith("away"):
            return round(probs["away"] * 100, 2)
        return 0.0

    if "over/under" in market or "over under" in market:
        import re

        line_match = re.search(r"(\d+\.?\d*)", prediction.market)
        line = float(line_match.group(1)) if line_match else 2.5
        current_total = home_score + away_score
        lambda_total = lambda_home + lambda_away
        needed = max(0, math.floor(line) + 1 - current_total)
        p_at_least_needed = 1.0 - _poisson_cdf_le(needed - 1, lambda_total)
        predicted_side = predicted.strip().lower()
        if "over" in predicted_side:
            return round(p_at_least_needed * 100, 2)
        if "under" in predicted_side:
            return round((1 - p_at_least_needed) * 100, 2)
        return 0.0

    if "both teams to score" in market or "btts" in market:
        home_scored = home_score > 0
        away_scored = away_score > 0
        if home_scored and away_scored:
            yes_prob = 1.0
        elif not home_scored and not away_scored:
            yes_prob = (1 - math.exp(-lambda_home)) * (1 - math.exp(-lambda_away))
        elif home_scored:
            yes_prob = 1 - math.exp(-lambda_away)
        else:
            yes_prob = 1 - math.exp(-lambda_home)
        predicted_side = predicted.strip().lower()
        if "yes" in predicted_side:
            return round(yes_prob * 100, 2)
        if "no" in predicted_side:
            return round((1 - yes_prob) * 100, 2)
        return 0.0

    return 0.0


# ---------------------------------------------------------------------------
# Tennis fulfillment
# ---------------------------------------------------------------------------
def _parse_tennis_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize tennis snapshot fields (set scores, current game, point)."""
    return {
        "home_sets": int(snapshot.get("home_sets") or 0),
        "away_sets": int(snapshot.get("away_sets") or 0),
        "home_games_current": int(snapshot.get("home_games_current") or 0),
        "away_games_current": int(snapshot.get("away_games_current") or 0),
        "home_point": snapshot.get("home_point") or "0",
        "away_point": snapshot.get("away_point") or "0",
        "best_of": int(snapshot.get("best_of") or 3),
    }


def _tennis_match_winner_fulfillment(state: Dict[str, Any]) -> float:
    """Simple set-based win probability for tennis match winner."""
    home_sets = state["home_sets"]
    away_sets = state["away_sets"]
    home_games = state["home_games_current"]
    away_games = state["away_games_current"]
    best_of = state["best_of"]
    sets_to_win = (best_of // 2) + 1  # 2 for best-of-3, 3 for best-of-5

    if home_sets >= sets_to_win:
        return 100.0
    if away_sets >= sets_to_win:
        return 0.0

    # Base probability from sets won.
    set_factor = (home_sets - away_sets) * 25.0
    # Add current game pressure.
    game_diff = home_games - away_games
    game_factor = max(-15, min(15, game_diff * 3))
    # Point pressure (approximate numeric value).
    point_map = {"0": 0, "15": 1, "30": 2, "40": 3, "AD": 4}
    hp = point_map.get(str(state["home_point"]).upper(), 0)
    ap = point_map.get(str(state["away_point"]).upper(), 0)
    point_factor = (hp - ap) * 2

    base = 50.0 + set_factor + game_factor + point_factor
    return round(max(5.0, min(95.0, base)), 2)


def _tennis_total_sets_fulfillment(state: Dict[str, Any], predicted: str) -> float:
    """Fulfillment for Total Sets Over/Under.

    Line is 2.5 for best-of-3 and 3.5 for best-of-5 (Grand Slams). It is taken
    from the predicted outcome string when present, otherwise derived from the
    snapshot's best_of.
    """
    home_sets = state["home_sets"]
    away_sets = state["away_sets"]
    home_games = state["home_games_current"]
    away_games = state["away_games_current"]
    best_of = state.get("best_of") or 3
    sets_to_win = best_of // 2 + 1  # 2 (bo3) or 3 (bo5)

    line_match = re.search(r"(\d+(?:\.\d+)?)", predicted or "")
    line = float(line_match.group(1)) if line_match else (sets_to_win + 0.5)

    total_sets_played = home_sets + away_sets
    decided_by = home_sets == sets_to_win or away_sets == sets_to_win

    if total_sets_played > line:
        over_prob = 1.0
    elif decided_by and total_sets_played <= line:
        # Someone already reached the winning set count at or below the line.
        over_prob = 0.0
    else:
        # In the final set allowed under the line: closeness of the current set
        # is the only signal for whether the match pushes past the line.
        remaining_to_line = math.floor(line) + 1 - total_sets_played
        if remaining_to_line == 1:
            game_diff = abs(home_games - away_games)
            if game_diff >= 3:
                over_prob = 0.25
            elif game_diff == 2:
                over_prob = 0.45
            else:
                over_prob = 0.65
        elif remaining_to_line <= 0:
            over_prob = 0.0
        else:
            over_prob = 0.5

    predicted_side = predicted.strip().lower()
    if "over" in predicted_side:
        return round(over_prob * 100, 2)
    if "under" in predicted_side:
        return round((1 - over_prob) * 100, 2)
    return 0.0


def _tennis_set1_winner_fulfillment(state: Dict[str, Any], prediction: Prediction) -> float:
    """Fulfillment for Set 1 Winner from live set/game state (crude proxy).

    With exactly one set on the board, the set-1 winner is known. During set 1
    the games leader is favored. With 2+ sets played the aggregate state cannot
    tell who won set 1, so a neutral 50 is returned.
    """
    home_sets = state["home_sets"]
    away_sets = state["away_sets"]
    home_games = state["home_games_current"]
    away_games = state["away_games_current"]

    competitors = {c.side: c for c in prediction.match.competitors}
    p1 = competitors.get("player1")
    p2 = competitors.get("player2")
    predicted = _normalize_team_name(prediction.predicted_outcome or "")
    predicted_side = None
    if p1 and p1.competitor and _normalize_team_name(p1.competitor.name) == predicted:
        predicted_side = "home"
    elif p2 and p2.competitor and _normalize_team_name(p2.competitor.name) == predicted:
        predicted_side = "away"
    if predicted_side is None:
        return 50.0

    total_sets = home_sets + away_sets
    if total_sets == 1:
        winner_side = "home" if home_sets == 1 else "away"
        return 95.0 if predicted_side == winner_side else 5.0
    if total_sets >= 2:
        return 50.0

    game_diff = (home_games - away_games) if predicted_side == "home" else (away_games - home_games)
    prob = 50.0 + game_diff * 10.0
    return round(max(5.0, min(95.0, prob)), 2)


def _tennis_fulfillment(prediction: Prediction, snapshot: Dict[str, Any]) -> float:
    market = prediction.market.lower()
    norm = _normalize_snapshot(snapshot)
    state = {
        "home_sets": norm["home_sets"],
        "away_sets": norm["away_sets"],
        "home_games_current": norm["home_games_current"],
        "away_games_current": norm["away_games_current"],
        "home_point": norm["home_point"],
        "away_point": norm["away_point"],
        "best_of": norm["best_of"],
    }

    if "total aces" in market:
        return 0.0

    if "set 1 winner" in market:
        return _tennis_set1_winner_fulfillment(state, prediction)

    if "winner" in market or "match winner" in market:
        return _tennis_match_winner_fulfillment(state)

    if "total sets" in market:
        return _tennis_total_sets_fulfillment(state, prediction.predicted_outcome)

    return 0.0


# ---------------------------------------------------------------------------
# Snapshot processing
# ---------------------------------------------------------------------------
def _normalize_team_name(name: str) -> str:
    return " ".join(name.lower().split())


def compute_fulfillment(prediction: Prediction, snapshot: Dict[str, Any]) -> float:
    sport_code = prediction.match.sport.code if prediction.match.sport else ""
    if sport_code == "football":
        return _football_fulfillment(prediction, snapshot)
    if sport_code == "tennis":
        return _tennis_fulfillment(prediction, snapshot)
    return 0.0


def process_snapshots(db: Session, snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Process live snapshots and update prediction progress.

    Each snapshot must contain at least:
        matchId (str), minute (int), homeScore (int), awayScore (int),
        periodLabel (str, optional).

    For tennis, additional fields are used: homeSets, awaySets,
    homeGamesCurrent, awayGamesCurrent, homePoint, awayPoint, bestOf.
    """
    now = datetime.now(timezone.utc)
    summary = {
        "snapshots_received": len(snapshots),
        "matches_found": 0,
        "predictions_updated": 0,
        "errors": [],
        "bySport": {},
    }

    for snapshot in snapshots:
        match_id = snapshot.get("matchId")
        if not match_id:
            summary["errors"].append("Snapshot missing matchId")
            continue

        match = db.query(Match).filter(Match.external_id == str(match_id)).first()
        if not match:
            summary["errors"].append(f"Match not found: {match_id}")
            continue

        summary["matches_found"] += 1
        sport_name = match.sport.name if match.sport else "Unknown"
        sport_bucket = summary["bySport"].setdefault(
            sport_name,
            {"predictions_updated": 0, "avg_fulfillment": 0.0},
        )

        predictions = (
            db.query(Prediction)
            .filter(Prediction.match_id == match.id, Prediction.status == "PENDING")
            .all()
        )

        for pred in predictions:
            try:
                fulfillment = compute_fulfillment(pred, snapshot)
            except Exception as exc:  # pragma: no cover
                summary["errors"].append(
                    f"Error computing fulfillment for {pred.id}: {exc}"
                )
                fulfillment = 0.0

            progress = PredictionProgress(
                id=uuid.uuid4(),
                prediction_id=pred.id,
                match_id=match.id,
                snapshot_at=now,
                minute=int(snapshot.get("minute") or 0),
                period_label=snapshot.get("periodLabel") or "",
                home_score=int(snapshot.get("homeScore") or 0),
                away_score=int(snapshot.get("awayScore") or 0),
                fulfillment_percent=fulfillment,
                notes=snapshot.get("notes") or "",
            )
            db.add(progress)

            pred.live_fulfillment_percent = fulfillment
            summary["predictions_updated"] += 1
            sport_bucket["predictions_updated"] += 1

    db.commit()

    # Compute averages per sport after commit.
    for sport_name, bucket in summary["bySport"].items():
        # Average across the latest snapshot of each pending prediction
        # belonging to that sport.
        sport_code = sport_name.lower()
        # This is a rough approximation; we report the overall average below.
        bucket["avg_fulfillment"] = 0.0

    if summary["predictions_updated"]:
        # Overall average fulfillment from the predictions we just touched.
        total_fulfillment = 0.0
        count = 0
        for snapshot in snapshots:
            match = db.query(Match).filter(
                Match.external_id == str(snapshot.get("matchId"))
            ).first()
            if not match:
                continue
            preds = (
                db.query(Prediction)
                .filter(Prediction.match_id == match.id, Prediction.status == "PENDING")
                .all()
            )
            for pred in preds:
                total_fulfillment += float(pred.live_fulfillment_percent or 0)
                count += 1
        summary["overall_avg_fulfillment"] = round(total_fulfillment / count, 2) if count else 0.0
    else:
        summary["overall_avg_fulfillment"] = 0.0

    summary["generatedAt"] = now.isoformat()
    return summary
