"""Feature engineering service for BrainBets predictions.

Builds per-match, per-competitor feature vectors from historical data
(form, surface-specific form, H2H, fatigue, etc.) and stores them in
feature_store for consumption by the prediction engine and future ML models.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from src.domain.models import (
    Competitor,
    CompetitorEloHistory,
    FeatureStore,
    Match,
    MatchCompetitor,
    MatchScore,
    Sport,
)


def _scores_for_side(
    mc: MatchCompetitor, score: Optional[MatchScore]
) -> Tuple[Optional[int], Optional[int]]:
    """Return (my_score, opponent_score) from a MatchScore row for the competitor's side.

    MatchCompetitor.score is not populated; the real result lives in
    match_scores (period FULL_TIME) from the home/player1 perspective.
    Tennis sides are player1/player2 (player1 == home), football home/away.
    """
    if score is None or score.home_score is None or score.away_score is None:
        return None, None
    if mc.side in ("home", "player1"):
        return score.home_score, score.away_score
    return score.away_score, score.home_score


class FeatureService:
    """Calculate and persist features for upcoming matches."""

    FEATURE_VERSION = "v2"

    def __init__(self, db: Session):
        self.db = db

    def build_features_for_matches(
        self,
        match_ids: Optional[List[str]] = None,
        sport_code: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Build features for a set of matches and persist them.

        If match_ids is provided, those matches are processed directly.
        Otherwise matches within [from_date, to_date] for the given sport
        are processed.
        """
        query = self.db.query(Match)

        if match_ids:
            query = query.filter(Match.id.in_(match_ids))
        # When no explicit IDs are provided we still restrict to matches that
        # are not cancelled/abandoned so feature building does not run on junk.
        if sport_code:
            query = query.join(Match.sport).filter(Sport.code == sport_code.lower())
        if from_date:
            query = query.filter(Match.match_date >= from_date)
        if to_date:
            query = query.filter(Match.match_date <= to_date)

        matches = query.all()
        created = 0
        updated = 0
        errors = []

        for match in matches:
            try:
                counts = self._build_features_for_match(match)
                created += counts.get("created", 0)
                updated += counts.get("updated", 0)
            except Exception as e:
                errors.append({"match_id": str(match.id), "error": str(e)})

        return {
            "version": self.FEATURE_VERSION,
            "matches_processed": len(matches),
            "features_created": created,
            "features_updated": updated,
            "errors": errors,
        }

    def _build_features_for_match(self, match: Match) -> Dict[str, int]:
        """Calculate features for both competitors of a single match."""
        sport_code = match.sport.code if match.sport else None
        if sport_code not in ("football", "tennis"):
            return {"created": 0, "updated": 0}

        competitors = {mc.side: mc for mc in match.competitors}
        if len(competitors) < 2:
            return {"created": 0, "updated": 0}

        created = 0
        updated = 0

        for side, mc in competitors.items():
            opponent_side = self._opponent_side(side)
            opponent_mc = competitors.get(opponent_side)
            opponent_id = opponent_mc.competitor_id if opponent_mc else None

            if sport_code == "football":
                features = self._compute_football_features(mc.competitor_id, match, side)
            else:
                features = self._compute_tennis_features(
                    mc.competitor_id, match, side, opponent_id
                )

            persisted = self._persist_feature(
                match_id=match.id,
                competitor_id=mc.competitor_id,
                features=features,
            )
            if persisted == "created":
                created += 1
            elif persisted == "updated":
                updated += 1

        return {"created": created, "updated": updated}

    def _opponent_side(self, side: str) -> Optional[str]:
        mapping = {
            "home": "away",
            "away": "home",
            "player1": "player2",
            "player2": "player1",
        }
        return mapping.get(side)

    def _persist_feature(
        self,
        match_id: Any,
        competitor_id: Any,
        features: Dict[str, Any],
    ) -> str:
        """Upsert a feature vector for a match+competitor."""
        existing = (
            self.db.query(FeatureStore)
            .filter(
                FeatureStore.match_id == match_id,
                FeatureStore.competitor_id == competitor_id,
                FeatureStore.feature_set_version == self.FEATURE_VERSION,
            )
            .first()
        )

        if existing:
            existing.features = features
            existing.created_at = datetime.now(timezone.utc)
            action = "updated"
        else:
            self.db.add(
                FeatureStore(
                    match_id=match_id,
                    competitor_id=competitor_id,
                    feature_set_version=self.FEATURE_VERSION,
                    features=features,
                )
            )
            action = "created"

        self.db.commit()
        return action

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def _competitor_finished_matches(
        self,
        competitor_id: Any,
        before_date: datetime,
        lookback_days: int = 365,
        limit: int = 50,
    ) -> List[Tuple[Match, MatchCompetitor, MatchScore]]:
        """Return finished matches for a competitor before a given date."""
        since = before_date - timedelta(days=lookback_days)

        rows = (
            self.db.query(Match, MatchCompetitor, MatchScore)
            .join(MatchCompetitor, Match.id == MatchCompetitor.match_id)
            .outerjoin(
                MatchScore,
                (Match.id == MatchScore.match_id) & (MatchScore.period == "FULL_TIME"),
            )
            .filter(MatchCompetitor.competitor_id == competitor_id)
            .filter(Match.status == "FINISHED")
            .filter(Match.match_date < before_date)
            .filter(Match.match_date >= since)
            .order_by(Match.match_date.desc())
            .limit(limit)
            .all()
        )
        return rows

    def _last_match_date(self, competitor_id: Any, before_date: datetime) -> Optional[datetime]:
        row = (
            self.db.query(Match.match_date)
            .join(MatchCompetitor, Match.id == MatchCompetitor.match_id)
            .filter(MatchCompetitor.competitor_id == competitor_id)
            .filter(Match.status == "FINISHED")
            .filter(Match.match_date < before_date)
            .order_by(Match.match_date.desc())
            .first()
        )
        return row[0] if row else None

    def _h2h_record(
        self,
        competitor_id: Any,
        opponent_id: Any,
        before_date: datetime,
        lookback_years: int = 5,
    ) -> Dict[str, int]:
        """Return H2H wins/losses between two competitors."""
        if not opponent_id:
            return {"wins": 0, "losses": 0, "matches": 0}

        since = before_date - timedelta(days=365 * lookback_years)

        # Find finished matches where both competitors played each other.
        subq = (
            self.db.query(Match.id)
            .join(MatchCompetitor, Match.id == MatchCompetitor.match_id)
            .filter(Match.status == "FINISHED")
            .filter(Match.match_date < before_date)
            .filter(Match.match_date >= since)
            .filter(MatchCompetitor.competitor_id.in_([competitor_id, opponent_id]))
            .group_by(Match.id)
            .having(func.count(MatchCompetitor.competitor_id.distinct()) == 2)
            .subquery()
        )

        wins = 0
        losses = 0
        matches = 0

        match_ids = [r[0] for r in self.db.query(subq.c.id).all()]
        for mid in match_ids:
            mcs = (
                self.db.query(MatchCompetitor)
                .filter(MatchCompetitor.match_id == mid)
                .all()
            )
            if len(mcs) != 2:
                continue
            c_map = {mc.competitor_id: mc for mc in mcs}
            if competitor_id not in c_map or opponent_id not in c_map:
                continue
            my_score = c_map[competitor_id].score or 0
            opp_score = c_map[opponent_id].score or 0
            matches += 1
            if my_score > opp_score:
                wins += 1
            elif my_score < opp_score:
                losses += 1

        return {"wins": wins, "losses": losses, "matches": matches}

    # ------------------------------------------------------------------
    # Football features
    # ------------------------------------------------------------------

    def _compute_football_features(
        self,
        competitor_id: Any,
        match: Match,
        side: str,
    ) -> Dict[str, Any]:
        """Compute football-specific features for one competitor."""
        before_date = match.match_date
        rows = self._competitor_finished_matches(
            competitor_id, before_date, lookback_days=365, limit=50
        )

        last_date = self._last_match_date(competitor_id, before_date)
        days_since_last_match = (
            (before_date - last_date).days if last_date else None
        )

        # Last N form
        last5 = rows[:5]
        last10 = rows[:10]

        def _aggregate(matches_rows: List[Tuple[Match, MatchCompetitor, MatchScore]]) -> Dict[str, Any]:
            played = 0
            wins = draws = losses = 0
            goals_for = goals_against = 0
            clean_sheets = btts = 0
            for m, mc, score in matches_rows:
                my_score, opp_score = _scores_for_side(mc, score)
                if my_score is None:
                    continue
                played += 1
                goals_for += my_score
                goals_against += opp_score
                if my_score > opp_score:
                    wins += 1
                elif my_score == opp_score:
                    draws += 1
                else:
                    losses += 1
                if opp_score == 0:
                    clean_sheets += 1
                if my_score > 0 and opp_score > 0:
                    btts += 1

            points = wins * 3 + draws
            return {
                "played": played,
                "wins": wins,
                "draws": draws,
                "losses": losses,
                "points": points,
                "points_per_game": round(points / played, 3) if played else 0,
                "goals_for": goals_for,
                "goals_against": goals_against,
                "goal_difference": goals_for - goals_against,
                "goals_for_avg": round(goals_for / played, 3) if played else 0,
                "goals_against_avg": round(goals_against / played, 3) if played else 0,
                "clean_sheets": clean_sheets,
                "btts": btts,
            }

        features = {
            "side": side,
            "days_since_last_match": days_since_last_match,
            "last_5": _aggregate(last5),
            "last_10": _aggregate(last10),
            "season": self._football_season_stats(competitor_id, match),
        }

        return features

    def _football_season_stats(
        self,
        competitor_id: Any,
        match: Match,
    ) -> Dict[str, Any]:
        """Aggregate stats for the current season up to the match date."""
        season = match.season
        if not season:
            return {}

        rows = (
            self.db.query(Match, MatchCompetitor, MatchScore)
            .join(MatchCompetitor, Match.id == MatchCompetitor.match_id)
            .outerjoin(
                MatchScore,
                (Match.id == MatchScore.match_id) & (MatchScore.period == "FULL_TIME"),
            )
            .filter(MatchCompetitor.competitor_id == competitor_id)
            .filter(Match.season == season)
            .filter(Match.status == "FINISHED")
            .filter(Match.match_date < match.match_date)
            .all()
        )

        played = 0
        wins = draws = losses = 0
        goals_for = goals_against = 0
        home_played = home_wins = 0
        away_played = away_wins = 0

        for m, mc, score in rows:
            my_score, opp_score = _scores_for_side(mc, score)
            if my_score is None:
                continue
            played += 1
            goals_for += my_score
            goals_against += opp_score
            is_home = mc.side == "home"
            if is_home:
                home_played += 1
            else:
                away_played += 1

            if my_score > opp_score:
                wins += 1
                if is_home:
                    home_wins += 1
                else:
                    away_wins += 1
            elif my_score == opp_score:
                draws += 1
            else:
                losses += 1

        return {
            "season": season,
            "played": played,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "points": wins * 3 + draws,
            "points_per_game": round((wins * 3 + draws) / played, 3) if played else 0,
            "goals_for": goals_for,
            "goals_against": goals_against,
            "home_played": home_played,
            "home_wins": home_wins,
            "away_played": away_played,
            "away_wins": away_wins,
        }

    # ------------------------------------------------------------------
    # Tennis features
    # ------------------------------------------------------------------

    def compute_tennis_features_for_match(
        self,
        match: Match,
    ) -> Dict[str, Dict[str, Any]]:
        """Return tennis-specific features for both competitors of a match."""
        competitors = {mc.side: mc for mc in match.competitors}
        p1 = competitors.get("player1")
        p2 = competitors.get("player2")
        if not p1 or not p2:
            return {}
        return {
            "player1": self._compute_tennis_features(
                p1.competitor_id, match, "player1", p2.competitor_id
            ),
            "player2": self._compute_tennis_features(
                p2.competitor_id, match, "player2", p1.competitor_id
            ),
        }

    def _compute_tennis_features(
        self,
        competitor_id: Any,
        match: Match,
        side: str,
        opponent_id: Any,
    ) -> Dict[str, Any]:
        """Compute tennis-specific features for one competitor."""
        before_date = match.match_date
        surface = (match.extra_data or {}).get("surface", "").lower()

        rows = self._competitor_finished_matches(
            competitor_id, before_date, lookback_days=730, limit=100
        )

        last_date = self._last_match_date(competitor_id, before_date)
        days_since_last_match = (
            (before_date - last_date).days if last_date else None
        )

        all_last20 = rows[:20]
        surface_rows = [
            (m, mc, s)
            for m, mc, s in rows
            if surface and ((m.extra_data or {}).get("surface", "").lower() == surface)
        ][:20]

        def _tennis_aggregate(
            matches_rows: List[Tuple[Match, MatchCompetitor, MatchScore]]
        ) -> Dict[str, Any]:
            played = 0
            wins = losses = 0
            sets_won = sets_lost = 0
            for m, mc, score in matches_rows:
                my_score, opp_score = _scores_for_side(mc, score)
                if my_score is None:
                    continue
                played += 1
                sets_won += my_score
                sets_lost += opp_score
                if my_score > opp_score:
                    wins += 1
                else:
                    losses += 1

            return {
                "played": played,
                "wins": wins,
                "losses": losses,
                "win_rate": round(wins / played, 3) if played else 0,
                "sets_won": sets_won,
                "sets_lost": sets_lost,
                "sets_difference": sets_won - sets_lost,
            }

        # Elo history snapshot
        elo_snapshot = (
            self.db.query(CompetitorEloHistory)
            .filter(CompetitorEloHistory.competitor_id == competitor_id)
            .filter(CompetitorEloHistory.calculated_at < before_date)
            .order_by(CompetitorEloHistory.calculated_at.desc())
            .first()
        )

        # Average aces per match from stored match statistics (last 20 with data)
        aces_values: List[float] = []
        for m, mc, _score in rows:
            if len(aces_values) >= 20:
                break
            stats = (m.extra_data or {}).get("score_stats") or {}
            home_aces = stats.get("homeAces")
            away_aces = stats.get("awayAces")
            if home_aces is None or away_aces is None:
                continue
            is_home = mc.side in ("player1", "home")
            try:
                aces_values.append(float(home_aces if is_home else away_aces))
            except (TypeError, ValueError):
                continue

        # Serve/return profile and tiebreak record from stored match statistics
        from src.application.tennis_stats_service import aggregate_serve_stats

        serve_overall = aggregate_serve_stats(
            [(m, mc) for m, mc, _s in rows], max_matches=20
        )
        serve_surface = aggregate_serve_stats(
            [(m, mc) for m, mc, _s in surface_rows], max_matches=20
        )

        def _matches_in_window(days: int) -> int:
            since = before_date - timedelta(days=days)
            return sum(1 for m, _, _ in rows if since <= m.match_date < before_date)

        features = {
            "side": side,
            "surface": surface,
            "days_since_last_match": days_since_last_match,
            "last_20": _tennis_aggregate(all_last20),
            "surface_last_20": _tennis_aggregate(surface_rows),
            "h2h": self._h2h_record(competitor_id, opponent_id, before_date),
            "elo_snapshot": {
                "elo_before": float(elo_snapshot.elo_before) if elo_snapshot else None,
                "surface": elo_snapshot.surface if elo_snapshot else None,
                "calculated_at": (
                    elo_snapshot.calculated_at.isoformat() if elo_snapshot else None
                ),
            },
            "matches_last_7_days": _matches_in_window(7),
            "matches_last_30_days": _matches_in_window(30),
            "matches_last_90_days": _matches_in_window(90),
            "aces_avg": round(sum(aces_values) / len(aces_values), 2) if aces_values else None,
            "aces_matches": len(aces_values),
            "hold_pct": serve_overall["holdPct"],
            "break_pct": serve_overall["breakPct"],
            "first_serve_pct": serve_overall["firstServePct"],
            "first_serve_won_pct": serve_overall["firstServeWonPct"],
            "serve_matches": serve_overall["serveMatches"],
            "surface_hold_pct": serve_surface["holdPct"],
            "surface_break_pct": serve_surface["breakPct"],
            "tiebreaks_played": serve_overall["tiebreaksPlayed"],
            "tiebreaks_won": serve_overall["tiebreaksWon"],
        }

        return features
