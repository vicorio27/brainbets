"""Application services orchestrating database reads and writes."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from src.domain.models import (
    Competitor,
    CompetitorStat,
    FeatureStore,
    League,
    Match,
    MatchCompetitor,
    MatchScore,
    Prediction,
    PredictionProgress,
    PredictionResult,
    Sport,
)
from src.infrastructure.repositories import (
    competitor_repository,
    match_repository,
    prediction_repository,
)
from src.presentation.schemas import (
    AccuracyMetrics,
    DashboardSummary,
    FootballMatch,
    MatchesResponse,
    Prediction as PredictionSchema,
    PredictionProgressResponse,
    PredictionProgressSnapshot,
    PredictionsResponse,
    PredictionWithResult,
    ResultItem,
    ResultsResponse,
    TennisMatch,
)
from src.application.poisson_service import expected_goals_for_fixture
from src.timezone import today_start_bogota, yesterday_start_bogota


class DataService:
    """Application service that orchestrates reads and writes from PostgreSQL."""

    def __init__(self, db: Session):
        self.db = db

    def get_match_surface_stats(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Career per-surface stats for both competitors of a tennis match."""
        from src.application.tennis_stats_service import get_match_surface_stats as _compute

        return _compute(self.db, match_id)

    def get_match_tournament_load(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Tournament-to-date physical load (matches, sets, games) for both players."""
        from src.application.tennis_stats_service import compute_tournament_load as _compute

        return _compute(self.db, match_id)

    def get_match_surface_load(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Recent per-surface effort (games) and rest days for both players."""
        from src.application.tennis_stats_service import compute_surface_load as _compute

        return _compute(self.db, match_id)

    def get_player_set_stats(self, target_date) -> Dict[str, Any]:
        """Average games per set by surface for players with a match that day."""
        from src.application.tennis_stats_service import compute_player_set_stats as _compute

        return _compute(self.db, target_date)

    def get_match_serve_stats(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Serve/return profile (hold/break %, 1st serve, tiebreaks) per player."""
        from src.application.tennis_stats_service import compute_match_serve_stats as _compute

        return _compute(self.db, match_id)

    def get_prediction_reliability(
        self, player: Optional[str] = None, surface: Optional[str] = None, min_sample: int = 4
    ) -> Dict[str, Any]:
        """Hit rate of each prediction market per tennis player and surface."""
        from src.application.tennis_stats_service import compute_prediction_reliability as _compute

        return _compute(self.db, player=player, surface=surface, min_sample=min_sample)

    def get_player_points_per_set(self, player: Optional[str] = None) -> Dict[str, Any]:
        """Average points won/lost per set position (1..5) per tennis player."""
        from src.application.tennis_stats_service import compute_player_points_per_set as _compute

        return _compute(self.db, player=player)

    def get_player_recent_by_surface(
        self, player: Optional[str] = None, limit: int = 3
    ) -> Dict[str, Any]:
        """Last N finished matches per surface for tennis players (from the DB)."""
        from src.application.tennis_stats_service import compute_player_recent_by_surface as _compute

        return _compute(self.db, player=player, limit=limit)

    # ------------------------------------------------------------------
    # Matches
    # ------------------------------------------------------------------
    def _competitor_stat(
        self,
        competitor_id: str,
        season: Optional[str] = None,
        league_id: Optional[str] = None,
        surface: Optional[str] = None,
    ) -> Optional[CompetitorStat]:
        """Fetch the most specific CompetitorStat available.

        Tries an exact match first, then falls back to a general stat
        (season=None, league_id=None) when season/league are provided.
        """
        base_query = self.db.query(CompetitorStat).filter(CompetitorStat.competitor_id == competitor_id)

        def _apply_filters(q):
            q = q.filter(CompetitorStat.season == season if season else CompetitorStat.season.is_(None))
            q = q.filter(CompetitorStat.league_id == league_id if league_id else CompetitorStat.league_id.is_(None))
            if surface:
                q = q.filter(CompetitorStat.surface == surface)
            else:
                q = q.filter(CompetitorStat.surface.is_(None))
            return q

        stat = _apply_filters(base_query).first()
        if stat:
            return stat

        # Fallback to general stat (no season/league) if a specific one was requested
        if season or league_id:
            fallback = base_query.filter(
                CompetitorStat.season.is_(None),
                CompetitorStat.league_id.is_(None),
            )
            if surface:
                fallback = fallback.filter(CompetitorStat.surface == surface)
            else:
                fallback = fallback.filter(CompetitorStat.surface.is_(None))
            return fallback.first()

        return None

    @staticmethod
    def _extract_event_id(external_id: Optional[str]) -> Optional[str]:
        """Return the provider-specific event id from a prefixed external_id.

        Live API workflows expect the numeric event id (e.g. '12345') rather
        than the stored prefixed form ('TENNIS-12345' or 'FOOTBALL-12345').
        """
        if not external_id:
            return None
        parts = external_id.split("-", 1)
        return parts[1] if len(parts) == 2 else external_id

    def _match_features(self, match: Match) -> Optional[dict]:
        """Return v2 feature vectors for each side of a match, if available."""
        features = (
            self.db.query(FeatureStore)
            .filter(
                FeatureStore.match_id == match.id,
                FeatureStore.feature_set_version == "v2",
            )
            .all()
        )
        if not features:
            return None
        return {f.features.get("side"): f.features for f in features if f.features.get("side")}

    def _match_to_football_schema(self, match: Match) -> Optional[FootballMatch]:
        home = next((c for c in match.competitors if c.side == "home"), None)
        away = next((c for c in match.competitors if c.side == "away"), None)
        if not home or not away:
            return None

        # Elo ratings are general (no season/league); Poisson params are season/league-specific
        home_elo_stat = self._competitor_stat(str(home.competitor_id))
        away_elo_stat = self._competitor_stat(str(away.competitor_id))
        home_poisson_stat = self._competitor_stat(
            str(home.competitor_id), season=match.season, league_id=str(match.league_id) if match.league_id else None
        )
        away_poisson_stat = self._competitor_stat(
            str(away.competitor_id), season=match.season, league_id=str(match.league_id) if match.league_id else None
        )

        home_elo = float(home_elo_stat.current_elo) if home_elo_stat and home_elo_stat.current_elo else None
        away_elo = float(away_elo_stat.current_elo) if away_elo_stat and away_elo_stat.current_elo else None

        home_poisson = (home_poisson_stat.extra_data or {}).get("poisson", {}) if home_poisson_stat else {}
        away_poisson = (away_poisson_stat.extra_data or {}).get("poisson", {}) if away_poisson_stat else {}

        expected_home, expected_away, _ = expected_goals_for_fixture(
            self.db,
            str(home.competitor_id),
            str(away.competitor_id),
            match.season or "",
            str(match.league_id) if match.league_id else None,
        )

        meta = match.extra_data or {}
        match_features = self._match_features(match)
        return FootballMatch(
            matchId=match.external_id or str(match.id),
            eventId=self._extract_event_id(match.external_id),
            homeTeam=home.competitor.name,
            awayTeam=away.competitor.name,
            league=match.league.name if match.league else "Unknown",
            eventDate=match.match_date.strftime("%Y-%m-%d") if match.match_date else None,
            eventTime=match.match_date.strftime("%H:%M") if match.match_date else None,
            status=match.status,
            homePosition=home.pre_match_ranking,
            awayPosition=away.pre_match_ranking,
            homeForm=home.pre_match_form,
            awayForm=away.pre_match_form,
            homeXg=home.extra_data.get("expected_goals") if home.extra_data else None,
            awayXg=away.extra_data.get("expected_goals") if away.extra_data else None,
            homeXgAgainst=meta.get("home_xg_against"),
            awayXgAgainst=meta.get("away_xg_against"),
            homeCorners=home.extra_data.get("corners_avg") if home.extra_data else None,
            awayCorners=away.extra_data.get("corners_avg") if away.extra_data else None,
            headToHead=meta.get("head_to_head"),
            homeFormStats=meta.get("home_form_stats"),
            awayFormStats=meta.get("away_form_stats"),
            leagueStandings=meta.get("league_standings"),
            statsDataQuality=meta.get("stats_data_quality"),
            homeElo=home_elo,
            awayElo=away_elo,
            homeAttack=home_poisson.get("home_attack"),
            homeDefense=home_poisson.get("home_defense"),
            awayAttack=away_poisson.get("away_attack"),
            awayDefense=away_poisson.get("away_defense"),
            expectedHomeGoals=round(expected_home, 3) if expected_home is not None else None,
            expectedAwayGoals=round(expected_away, 3) if expected_away is not None else None,
            homeOdds=float(home.pre_match_odds) if home and home.pre_match_odds is not None else None,
            awayOdds=float(away.pre_match_odds) if away and away.pre_match_odds is not None else None,
            drawOdds=float(meta.get('draw_odds')) if meta and meta.get('draw_odds') is not None else None,
            expertConsensus=meta.get("expert_consensus"),
            features=match_features,
        )

    def _tennis_recent_form(
        self,
        competitor_id: str,
        before_date: Optional[datetime] = None,
        limit: int = 5,
    ) -> Optional[str]:
        """Build a W/L form string from the competitor's last finished matches."""
        query = (
            self.db.query(Match, MatchCompetitor, MatchScore)
            .join(MatchCompetitor, Match.id == MatchCompetitor.match_id)
            .outerjoin(MatchScore, Match.id == MatchScore.match_id)
            .filter(MatchCompetitor.competitor_id == competitor_id)
            .filter(Match.status == "FINISHED")
            .filter(MatchScore.period == "FULL_TIME")
        )
        if before_date is not None:
            query = query.filter(Match.match_date < before_date)
        rows = (
            query.order_by(desc(Match.match_date))
            .limit(limit)
            .all()
        )
        if not rows:
            return None
        form_chars = []
        for m, mc, score in rows:
            my_score = mc.score or 0
            opp = (
                self.db.query(MatchCompetitor)
                .filter(
                    MatchCompetitor.match_id == m.id,
                    MatchCompetitor.competitor_id != competitor_id,
                )
                .first()
            )
            opp_score = opp.score if opp else 0
            if my_score > opp_score:
                form_chars.append("W")
            elif my_score < opp_score:
                form_chars.append("L")
            else:
                form_chars.append("D")
        return "".join(reversed(form_chars))

    def _match_to_tennis_schema(self, match: Match) -> Optional[TennisMatch]:
        p1 = next((c for c in match.competitors if c.side == "player1"), None)
        p2 = next((c for c in match.competitors if c.side == "player2"), None)
        if not p1 or not p2:
            return None

        surface = (match.extra_data or {}).get("surface")
        overall_p1 = self._competitor_stat(str(p1.competitor_id))
        overall_p2 = self._competitor_stat(str(p2.competitor_id))
        surface_p1 = self._competitor_stat(str(p1.competitor_id), surface=surface) if surface else None
        surface_p2 = self._competitor_stat(str(p2.competitor_id), surface=surface) if surface else None

        meta = match.extra_data or {}
        match_features = self._match_features(match)
        form_p1 = p1.pre_match_form or self._tennis_recent_form(
            str(p1.competitor_id), before_date=match.match_date, limit=5
        )
        form_p2 = p2.pre_match_form or self._tennis_recent_form(
            str(p2.competitor_id), before_date=match.match_date, limit=5
        )
        return TennisMatch(
            matchId=match.external_id or str(match.id),
            eventId=self._extract_event_id(match.external_id),
            player1=p1.competitor.name,
            player2=p2.competitor.name,
            tournament=match.league.name if match.league else "Unknown",
            eventDate=match.match_date.strftime("%Y-%m-%d") if match.match_date else None,
            eventTime=match.match_date.strftime("%H:%M") if match.match_date else None,
            status=match.status,
            rankingPlayer1=p1.pre_match_ranking,
            rankingPlayer2=p2.pre_match_ranking,
            surface=surface,
            formPlayer1=form_p1,
            formPlayer2=form_p2,
            h2h=meta.get("h2h"),
            acesAvgPlayer1=p1.extra_data.get("aces_avg") if p1.extra_data else None,
            acesAvgPlayer2=p2.extra_data.get("aces_avg") if p2.extra_data else None,
            eloPlayer1=float(overall_p1.current_elo) if overall_p1 and overall_p1.current_elo else None,
            eloPlayer2=float(overall_p2.current_elo) if overall_p2 and overall_p2.current_elo else None,
            eloSurfacePlayer1=float(surface_p1.current_elo) if surface_p1 and surface_p1.current_elo else None,
            eloSurfacePlayer2=float(surface_p2.current_elo) if surface_p2 and surface_p2.current_elo else None,
            oddsPlayer1=float(p1.pre_match_odds) if p1 and p1.pre_match_odds is not None else None,
            oddsPlayer2=float(p2.pre_match_odds) if p2 and p2.pre_match_odds is not None else None,
            oddsMarkets=meta.get("odds_markets"),
            tournamentTier=meta.get("tournament_tier"),
            groundType=meta.get("ground_type"),
            countryPlayer1=p1.competitor.country,
            countryPlayer2=p2.competitor.country,
            features=match_features,
        )

    def get_latest_matches(self) -> Optional[MatchesResponse]:
        matches = match_repository.list(self.db, limit=100)
        if not matches:
            return None

        football = []
        tennis = []
        latest_created = None

        for match in matches:
            if latest_created is None or match.created_at > latest_created:
                latest_created = match.created_at

            if match.sport and match.sport.code == "football":
                schema = self._match_to_football_schema(match)
                if schema:
                    football.append(schema)
            elif match.sport and match.sport.code == "tennis":
                schema = self._match_to_tennis_schema(match)
                if schema:
                    tennis.append(schema)

        return MatchesResponse(
            generatedAt=(latest_created or datetime.now(timezone.utc)).isoformat(),
            tennis=tennis,
            football=football,
        )

    def _matches_by_sport(
        self,
        date_from,
        date_to,
        sport_code: str,
        skip: int,
        limit: int,
        sort: str,
    ):
        from datetime import datetime, time, timezone

        start_dt = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(date_to, time.max, tzinfo=timezone.utc)

        query = (
            self.db.query(Match)
            .filter(Match.match_date >= start_dt, Match.match_date <= end_dt)
            .join(Match.sport)
            .filter(Sport.code == sport_code)
            .outerjoin(Match.league)
        )
        total = query.count()
        order = (
            League.tier.asc(),
            Match.match_date.desc() if sort == "desc" else Match.match_date.asc(),
        )
        matches = query.order_by(*order).offset(skip).limit(limit).all()
        return matches, total

    def get_matches_by_date(
        self,
        date_from,
        date_to,
        sport: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        sort: str = "desc",
    ) -> Optional[MatchesResponse]:
        from datetime import datetime, time, timezone

        if sport:
            matches, total = self._matches_by_sport(
                date_from, date_to, sport.lower(), skip, limit, sort
            )
            if not matches:
                return None
        else:
            tennis_matches, tennis_total = self._matches_by_sport(
                date_from, date_to, "tennis", skip, limit, sort
            )
            football_matches, football_total = self._matches_by_sport(
                date_from, date_to, "football", skip, limit, sort
            )
            matches = list(tennis_matches) + list(football_matches)
            total = tennis_total + football_total
            if not matches:
                return None

        football = []
        tennis = []
        latest_created = None

        for match in matches:
            if latest_created is None or match.created_at > latest_created:
                latest_created = match.created_at

            if match.sport and match.sport.code == "football":
                schema = self._match_to_football_schema(match)
                if schema:
                    football.append(schema)
            elif match.sport and match.sport.code == "tennis":
                schema = self._match_to_tennis_schema(match)
                if schema:
                    tennis.append(schema)

        return MatchesResponse(
            generatedAt=(latest_created or datetime.now(timezone.utc)).isoformat(),
            tennis=tennis,
            football=football,
            total=total,
            skip=skip,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # Predictions
    # ------------------------------------------------------------------
    def _prediction_to_schema(self, prediction: Prediction) -> PredictionSchema:
        home_name = away_name = None
        if prediction.match:
            for mc in prediction.match.competitors:
                name = mc.competitor.name if mc.competitor else None
                if mc.side in ("home", "player1"):
                    home_name = name
                elif mc.side in ("away", "player2"):
                    away_name = name
        sport_code = prediction.match.sport.code if prediction.match and prediction.match.sport else "unknown"
        from src.application.calibration_service import apply_calibration

        calibrated_conf, calibrated_ev = apply_calibration(
            sport_code,
            prediction.market,
            prediction.confidence,
            prediction.reasoning_data,
            prediction.predicted_outcome,
            home_name,
            away_name,
        )
        return PredictionSchema(
            predictionId=str(prediction.id),
            matchId=prediction.match.external_id if prediction.match else None,
            sport=sport_code,
            market=prediction.market,
            prediction=prediction.predicted_outcome,
            confidence=prediction.confidence,
            reasoning=prediction.reasoning or "",
            naturalLanguageReasoning=prediction.natural_language_reasoning or "",
            status=prediction.status,
            probabilities=prediction.probabilities or {},
            modelContributions=prediction.model_contributions or {},
            reasoningData=prediction.reasoning_data or {},
            eventDate=prediction.match.match_date.strftime("%Y-%m-%d") if prediction.match and prediction.match.match_date else None,
            createdAt=prediction.created_at.isoformat() if prediction.created_at else None,
            homeName=home_name,
            awayName=away_name,
            expectedValue=float(prediction.expected_value) if prediction.expected_value is not None else None,
            kellyFraction=float(prediction.kelly_fraction) if prediction.kelly_fraction is not None else None,
            calibratedConfidence=calibrated_conf,
            calibratedExpectedValue=calibrated_ev,
        )

    def get_latest_predictions(self) -> Optional[PredictionsResponse]:
        predictions = prediction_repository.list(self.db, limit=500)
        if not predictions:
            return None

        latest_created = max((p.created_at for p in predictions), default=datetime.now(timezone.utc))
        return PredictionsResponse(
            generatedAt=latest_created.isoformat() if latest_created else datetime.now(timezone.utc).isoformat(),
            predictions=[self._prediction_to_schema(p) for p in predictions],
        )

    def get_predictions_history(
        self,
        sport: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        match_id: Optional[str] = None,
        name_query: Optional[str] = None,
    ) -> PredictionsResponse:
        from datetime import datetime as _dt, timezone as _tz
        from sqlalchemy import and_, not_

        # Always join Prediction.match: the stale-PENDING filter below references
        # Match.match_date, and without the join SQLAlchemy adds `matches` to the
        # FROM clause as a cartesian product (inflating total and rows). The join
        # is many-to-one, so it never duplicates prediction rows.
        base_query = self.db.query(Prediction).join(Prediction.match)
        if match_id:
            base_query = base_query.filter(Match.external_id == match_id)
        if name_query and name_query.strip():
            # Correlated EXISTS: matches predictions whose match has ANY competitor
            # (player or team) with a name containing the query, without
            # duplicating rows in the main query (2 competitors per match).
            pattern = f"%{name_query.strip()}%"
            name_exists = (
                self.db.query(MatchCompetitor.id)
                .join(Competitor, MatchCompetitor.competitor_id == Competitor.id)
                .filter(MatchCompetitor.match_id == Prediction.match_id)
                .filter(Competitor.name.ilike(pattern))
                .exists()
            )
            base_query = base_query.filter(name_exists)
        if sport:
            base_query = base_query.join(Match.sport).filter(Sport.code == sport)
        if date_from:
            base_query = base_query.filter(Match.match_date >= date_from)
        if date_to:
            base_query = base_query.filter(Match.match_date <= date_to)
        if status:
            base_query = base_query.filter(Prediction.status == status)

        # Hide stale PENDING predictions whose match is older than the validation
        # window (yesterday onwards). This prevents abandoned/old predictions from
        # cluttering the frontend history view. Skipped when filtering by an
        # explicit match_id: a per-match lookup must return all its predictions.
        if not match_id:
            now = _dt.now(_tz.utc)
            yesterday_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
            base_query = base_query.filter(
                not_(
                    and_(
                        Prediction.status.in_(["PENDING", "LOW_CONFIDENCE"]),
                        Match.match_date < yesterday_start,
                    )
                )
            )

        total = base_query.count()
        predictions = (
            base_query.options(
                joinedload(Prediction.match)
                .joinedload(Match.competitors)
                .joinedload(MatchCompetitor.competitor)
            )
            .order_by(desc(Prediction.created_at))
            .offset(skip)
            .limit(limit)
            .all()
        )
        latest_created = max(
            (p.created_at for p in predictions),
            default=_dt.now(_tz.utc),
        )
        return PredictionsResponse(
            generatedAt=latest_created.isoformat(),
            predictions=[self._prediction_to_schema(p) for p in predictions],
            total=total,
            skip=skip,
            limit=limit,
        )

    def get_prediction_result(self, prediction_id: str) -> Optional[PredictionWithResult]:
        prediction = prediction_repository.get(self.db, prediction_id)
        if not prediction:
            return None

        result = None
        if prediction.result:
            result = ResultItem(
                predictionId=str(prediction.id),
                success=prediction.result.is_successful,
                actualResult=prediction.result.actual_outcome or "Pending",
                validationReason=prediction.result.validation_notes or "",
                matchScore=prediction.result.match_score_snapshot,
            )

        return PredictionWithResult(
            prediction=self._prediction_to_schema(prediction),
            result=result,
        )

    def get_prediction_progress(self, prediction_id: str) -> Optional[PredictionProgressResponse]:
        prediction = prediction_repository.get(self.db, prediction_id)
        if not prediction:
            return None

        snapshots = (
            self.db.query(PredictionProgress)
            .filter(PredictionProgress.prediction_id == prediction_id)
            .order_by(PredictionProgress.snapshot_at.asc())
            .all()
        )

        return PredictionProgressResponse(
            predictionId=str(prediction.id),
            matchId=prediction.match.external_id if prediction.match else None,
            sport=prediction.match.sport.code if prediction.match and prediction.match.sport else None,
            market=prediction.market,
            predictedOutcome=prediction.predicted_outcome,
            snapshots=[
                PredictionProgressSnapshot(
                    snapshotAt=s.snapshot_at.isoformat() if s.snapshot_at else "",
                    minute=s.minute or 0,
                    periodLabel=s.period_label,
                    homeScore=s.home_score or 0,
                    awayScore=s.away_score or 0,
                    fulfillmentPercent=float(s.fulfillment_percent) if s.fulfillment_percent else 0.0,
                    notes=s.notes,
                )
                for s in snapshots
            ],
        )

    # ------------------------------------------------------------------
    # Results / Accuracy
    # ------------------------------------------------------------------
    def get_latest_results(self) -> Optional[ResultsResponse]:
        results = (
            self.db.query(PredictionResult)
            .order_by(PredictionResult.validated_at.desc())
            .limit(1000)
            .all()
        )
        if not results:
            return None

        latest_validated = max((r.validated_at for r in results), default=datetime.now(timezone.utc))
        return ResultsResponse(
            generatedAt=latest_validated.isoformat() if latest_validated else datetime.now(timezone.utc).isoformat(),
            results=[
                ResultItem(
                    predictionId=str(r.prediction_id),
                    success=r.is_successful,
                    actualResult=r.actual_outcome or "Pending",
                    validationReason=r.validation_notes or "",
                    matchScore=r.match_score_snapshot,
                )
                for r in results
            ],
        )

    def get_accuracy(self, since: Optional[datetime] = None) -> AccuracyMetrics:
        query = self.db.query(PredictionResult)
        if since is not None:
            query = query.filter(PredictionResult.validated_at >= since)
        results = query.all()
        if not results:
            return AccuracyMetrics(
                totalPredictions=0,
                successful=0,
                failed=0,
                accuracy=0.0,
                accuracyTennis=0.0,
                accuracyFootball=0.0,
            )

        total = len(results)
        successful = sum(1 for r in results if r.is_successful is True)
        failed = sum(1 for r in results if r.is_successful is False)

        tennis_results = [r for r in results if r.prediction.match.sport.code == "tennis"]
        football_results = [r for r in results if r.prediction.match.sport.code == "football"]

        def _accuracy(items: List[PredictionResult]) -> float:
            if not items:
                return 0.0
            wins = sum(1 for r in items if r.is_successful is True)
            valid = sum(1 for r in items if r.is_successful is not None)
            return round(wins / valid * 100, 2) if valid > 0 else 0.0

        return AccuracyMetrics(
            totalPredictions=total,
            successful=successful,
            failed=failed,
            accuracy=round(successful / total * 100, 2) if total > 0 else 0.0,
            accuracyTennis=_accuracy(tennis_results),
            accuracyFootball=_accuracy(football_results),
        )

    def get_accuracy_by_day(self, days: int = 30) -> Dict[str, Any]:
        """Validated-prediction accuracy grouped by the match's day (Bogota).

        Uses the match date, not validated_at, so a match's predictions all
        land on the day it was played regardless of when validation ran.
        """
        from sqlalchemy import func

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        rows = (
            self.db.query(
                func.date(func.timezone("America/Bogota", Match.match_date)).label("day"),
                Sport.code.label("sport"),
                PredictionResult.is_successful.label("ok"),
            )
            .select_from(PredictionResult)
            .join(Prediction, Prediction.id == PredictionResult.prediction_id)
            .join(Match, Match.id == Prediction.match_id)
            .join(Sport, Sport.id == Match.sport_id)
            .filter(PredictionResult.is_successful.isnot(None))
            .filter(Match.match_date >= cutoff)
            .all()
        )

        by_day: Dict[str, Dict[str, Any]] = {}
        for day, sport, ok in rows:
            key = day.isoformat() if hasattr(day, "isoformat") else str(day)
            d = by_day.setdefault(
                key,
                {
                    "date": key,
                    "total": 0,
                    "successful": 0,
                    "tennisTotal": 0,
                    "tennisSuccessful": 0,
                    "footballTotal": 0,
                    "footballSuccessful": 0,
                },
            )
            d["total"] += 1
            d["successful"] += 1 if ok else 0
            if sport == "tennis":
                d["tennisTotal"] += 1
                d["tennisSuccessful"] += 1 if ok else 0
            elif sport == "football":
                d["footballTotal"] += 1
                d["footballSuccessful"] += 1 if ok else 0

        def _pct(n: int, d: int) -> Optional[float]:
            return round(n / d * 100, 1) if d else None

        days_out = []
        for d in sorted(by_day.values(), key=lambda x: x["date"], reverse=True):
            days_out.append(
                {
                    "date": d["date"],
                    "total": d["total"],
                    "successful": d["successful"],
                    "failed": d["total"] - d["successful"],
                    "accuracy": _pct(d["successful"], d["total"]),
                    "accuracyTennis": _pct(d["tennisSuccessful"], d["tennisTotal"]),
                    "accuracyFootball": _pct(d["footballSuccessful"], d["footballTotal"]),
                    "tennisTotal": d["tennisTotal"],
                    "footballTotal": d["footballTotal"],
                }
            )
        return {"days": days_out}

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    def get_dashboard_summary(self) -> DashboardSummary:
        summary = DashboardSummary()

        latest_match = match_repository.get_latest(self.db)
        if latest_match:
            summary.lastMatchesUpdate = latest_match.created_at.isoformat() if latest_match.created_at else None
            today_start = today_start_bogota()
            summary.todayMatches = (
                self.db.query(Match)
                .filter(Match.match_date >= today_start)
                .count()
            )
            latest_start = today_start - timedelta(days=1)
            summary.latestMatches = (
                self.db.query(Match)
                .filter(Match.match_date >= latest_start)
                .count()
            )

        latest_prediction = prediction_repository.get_latest(self.db)
        if latest_prediction:
            summary.lastPredictionsUpdate = latest_prediction.created_at.isoformat() if latest_prediction.created_at else None
            today_start = today_start_bogota()
            summary.todayPredictions = (
                self.db.query(Prediction)
                .filter(Prediction.created_at >= today_start)
                .count()
            )
            latest_start = today_start - timedelta(days=1)
            summary.latestPredictions = (
                self.db.query(Prediction)
                .filter(Prediction.created_at >= latest_start)
                .count()
            )
            summary.latestPredictedMatches = (
                self.db.query(Prediction.match_id)
                .filter(Prediction.created_at >= latest_start)
                .distinct()
                .count()
            )

        latest_result = (
            self.db.query(PredictionResult)
            .order_by(PredictionResult.validated_at.desc())
            .first()
        )
        if latest_result:
            summary.lastResultsUpdate = latest_result.validated_at.isoformat() if latest_result.validated_at else None
            summary.todayAccuracy = self.get_accuracy().accuracy
            latest_start = yesterday_start_bogota()
            summary.latestAccuracy = self.get_accuracy(since=latest_start).accuracy

        return summary

    # ------------------------------------------------------------------
    # Internal write helpers
    # ------------------------------------------------------------------
    def ensure_sport(self, code: str, name: str) -> Sport:
        sport = self.db.query(Sport).filter(Sport.code == code).first()
        if not sport:
            sport = Sport(code=code, name=name)
            self.db.add(sport)
            self.db.commit()
            self.db.refresh(sport)
        return sport
