"""Tennis stats enrichment service.

Computes head-to-head records from historical matches stored in PostgreSQL.
Used by the data collection workflow to replace placeholder H2H strings with
real data-backed values.
"""
import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from src.domain.models import (
    Competitor,
    CompetitorEloHistory,
    Match,
    MatchCompetitor,
    MatchScore,
    Prediction,
    PredictionResult,
    Sport,
)


def _normalize_name(name: str) -> str:
    """Normalize a player name for fuzzy matching.

    Removes accents, lowercases, strips initials like 'C.' and normalizes
    whitespace so variants like 'Carlos Alcaraz' and 'C. Alcaraz' match.
    """
    if not name:
        return ""
    normalized = unicodedata.normalize("NFKD", name)
    normalized = normalized.encode("ASCII", "ignore").decode("ASCII")
    normalized = normalized.lower()
    normalized = re.sub(r"\b[a-z]\.\s*", "", normalized)
    normalized = re.sub(r"[^\w\s]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _name_tokens_and_initials(name: str) -> Tuple[Set[str], Set[str]]:
    """Split a raw name into (word tokens, initials).

    'T. M. Etcheverry' -> ({'etcheverry'}, {'t', 'm'})
    'J-L. Struff' -> ({'struff'}, {'j', 'l'})
    'Tomas Martin Etcheverry' -> ({'tomas', 'martin', 'etcheverry'}, set())
    """
    if not name:
        return set(), set()
    # Treat hyphens as separators so 'J-L.' yields initials 'j' and 'l'.
    lowered = name.lower().replace("-", " ")
    initials = set(re.findall(r"\b([a-z])\.", lowered))
    tokens: Set[str] = set()
    for tok in _normalize_name(lowered).split():
        if len(tok) == 1:
            initials.add(tok)
        else:
            tokens.add(tok)
    return tokens, initials


def resolve_competitor_fuzzy(
    db: Session, sport_id: Any, name: str
) -> Optional[Competitor]:
    """Resolve a tennis competitor handling abbreviated provider names.

    Matching ladder: exact -> ilike -> normalized equality -> token-subset
    (all word tokens of one name contained in the other). When several
    token-subset candidates exist, initials from the abbreviated name break
    the tie ('F. Cerundolo' picks Francisco over Juan Manuel). A unique best
    candidate wins even with zero initial overlap ('J-L. Struff' still
    resolves to Jan-Lennard Struff). Returns None when ambiguous.
    """
    competitor = (
        db.query(Competitor)
        .filter(Competitor.sport_id == sport_id, Competitor.name == name)
        .first()
    )
    if competitor:
        return competitor

    competitor = (
        db.query(Competitor)
        .filter(Competitor.sport_id == sport_id, Competitor.name.ilike(name))
        .first()
    )
    if competitor:
        return competitor

    target = _normalize_name(name)
    if not target:
        return None

    candidates = db.query(Competitor).filter(Competitor.sport_id == sport_id).all()
    normalized_map: Dict[Any, str] = {}
    for candidate in candidates:
        normalized_map[candidate.id] = _normalize_name(candidate.name)
        if normalized_map[candidate.id] == target:
            return candidate

    # Token-subset matching for abbreviated names.
    target_tokens, target_initials = _name_tokens_and_initials(name)
    if not target_tokens:
        return None

    subset_matches: List[Tuple[Competitor, int]] = []
    for candidate in candidates:
        cand_normalized = normalized_map.get(candidate.id) or ""
        cand_tokens, _ = _name_tokens_and_initials(candidate.name)
        if not cand_tokens:
            continue
        if target_tokens <= cand_tokens or cand_tokens <= target_tokens:
            cand_initials = {t[0] for t in cand_normalized.split() if t}
            score = len(target_initials & cand_initials)
            subset_matches.append((candidate, score))

    if not subset_matches:
        return None
    if len(subset_matches) == 1:
        return subset_matches[0][0]

    best_score = max(score for _, score in subset_matches)
    best = [c for c, score in subset_matches if score == best_score]
    return best[0] if len(best) == 1 else None


def _find_competitor_by_name(
    db: Session, sport_id: Any, name: str
) -> Optional[Competitor]:
    """Find a tennis competitor by exact, normalized or token-subset name."""
    return resolve_competitor_fuzzy(db, sport_id, name)


def compute_tennis_h2h(
    db: Session,
    player1_name: str,
    player2_name: str,
    before_date: Optional[datetime] = None,
    limit: int = 10,
) -> Optional[Dict[str, Any]]:
    """Compute H2H record between two tennis players from finished DB matches.

    Returns a dict with wins/losses and a 'wins-losses' string compatible with
    the prediction engine, or None if no H2H data is available.
    """
    sport = db.query(Sport).filter(Sport.code == "tennis").first()
    if not sport:
        return None

    p1 = _find_competitor_by_name(db, sport.id, player1_name)
    p2 = _find_competitor_by_name(db, sport.id, player2_name)
    if not p1 or not p2:
        return None

    query = (
        db.query(Match)
        .join(MatchCompetitor, Match.id == MatchCompetitor.match_id)
        .filter(Match.sport_id == sport.id)
        .filter(Match.status == "FINISHED")
        .filter(MatchCompetitor.competitor_id.in_([p1.id, p2.id]))
    )
    if before_date is not None:
        query = query.filter(Match.match_date < before_date)

    matches = query.order_by(Match.match_date.desc()).all()

    h2h_matches = []
    for match in matches:
        competitor_ids = {c.side: c.competitor_id for c in match.competitors}
        sides = set(competitor_ids.values())
        if p1.id in sides and p2.id in sides:
            h2h_matches.append(match)
        if len(h2h_matches) >= limit:
            break

    if not h2h_matches:
        return None

    # Preload final match scores (one summary row per match expected for tennis)
    match_ids = [m.id for m in h2h_matches]
    scores = {
        s.match_id: s
        for s in db.query(MatchScore).filter(MatchScore.match_id.in_(match_ids)).all()
    }

    p1_wins = 0
    p2_wins = 0
    details = []
    for match in h2h_matches:
        c_map = {c.competitor_id: c for c in match.competitors}
        p1_mc = c_map.get(p1.id)
        p2_mc = c_map.get(p2.id)
        if not p1_mc or not p2_mc:
            continue

        score = scores.get(match.id)
        if score:
            # Map player1 -> home, player2 -> away
            p1_sets = score.home_score if p1_mc.side == "player1" else score.away_score
            p2_sets = score.home_score if p2_mc.side == "player1" else score.away_score
        else:
            p1_sets = p1_mc.score or 0
            p2_sets = p2_mc.score or 0

        if p1_sets is None or p2_sets is None:
            continue

        if p1_sets > p2_sets:
            p1_wins += 1
        elif p2_sets > p1_sets:
            p2_wins += 1
        else:
            continue

        details.append({
            "date": match.match_date.isoformat() if match.match_date else None,
            "player1_score": p1_sets,
            "player2_score": p2_sets,
        })

    total = p1_wins + p2_wins
    if total == 0:
        return None

    return {
        "player1_wins": p1_wins,
        "player2_wins": p2_wins,
        "matches": total,
        "h2h_string": f"{p1_wins}-{p2_wins}",
        "source": "db_historical",
        "details": details,
    }


def enrich_tennis_match(
    db: Session,
    raw: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Enrich a tennis match with H2H and FeatureService-derived stats.

    The returned dict contains both the H2H record and the rich per-player
    feature block (recent form, surface form, days since last match). It is
    safe to call for matches that have not been persisted yet; in that case
    only H2H is returned.
    """
    match_id = raw.get("matchId")
    player1 = raw.get("player1")
    player2 = raw.get("player2")
    event_date = raw.get("eventDate")

    before_date = None
    if event_date:
        try:
            before_date = datetime.strptime(event_date, "%Y-%m-%d")
        except Exception:
            pass

    result: Dict[str, Any] = {
        "h2h": None,
        "featureService": None,
    }

    h2h = compute_tennis_h2h(
        db, player1, player2, before_date=before_date, limit=10
    )
    if h2h:
        result["h2h"] = h2h

    if match_id:
        match = db.query(Match).filter(Match.external_id == match_id).first()
        if match:
            try:
                from src.application.feature_service import FeatureService
                features = FeatureService(db).compute_tennis_features_for_match(match)
                if features:
                    result["featureService"] = features
            except Exception:
                pass

    return result


_SURFACE_NORMALIZATION = (
    ("clay", ("clay", "polvo", "brick", "tierra batida")),
    ("grass", ("grass", "cesped", "césped", "hierba")),
    ("hard", ("hard", "cement", "cemento", "acrylic", "carpet", "indoor", "plexipave", "decoturf")),
)


def normalize_surface(raw: Optional[str]) -> Optional[str]:
    """Normalize a surface string to 'hard' | 'clay' | 'grass' (or None)."""
    s = (raw or "").strip().lower()
    if not s:
        return None
    for canonical, tokens in _SURFACE_NORMALIZATION:
        if any(tok in s for tok in tokens):
            return canonical
    return None


def compute_surface_career(db: Session, competitor_id: Any) -> Dict[str, Any]:
    """Career win-loss record per surface for a tennis competitor.

    Reads finished matches with FULL_TIME scores from match_scores and groups
    by normalized surface. Also returns the latest Elo per surface and overall
    from competitor_elo_history.
    """
    from src.application.feature_service import _scores_for_side

    rows = (
        db.query(Match, MatchCompetitor, MatchScore)
        .join(MatchCompetitor, Match.id == MatchCompetitor.match_id)
        .join(
            MatchScore,
            (Match.id == MatchScore.match_id) & (MatchScore.period == "FULL_TIME"),
        )
        .filter(MatchCompetitor.competitor_id == competitor_id)
        .filter(Match.status == "FINISHED")
        .all()
    )

    surfaces: Dict[str, Dict[str, Any]] = {}
    for m, mc, score in rows:
        surface = normalize_surface((m.extra_data or {}).get("surface"))
        if not surface:
            continue
        my_sets, opp_sets = _scores_for_side(mc, score)
        if my_sets is None:
            continue
        agg = surfaces.setdefault(
            surface, {"played": 0, "wins": 0, "losses": 0, "sets_won": 0, "sets_lost": 0}
        )
        agg["played"] += 1
        agg["sets_won"] += my_sets
        agg["sets_lost"] += opp_sets
        if my_sets > opp_sets:
            agg["wins"] += 1
        else:
            agg["losses"] += 1

    for agg in surfaces.values():
        agg["win_rate"] = round(agg["wins"] / agg["played"], 3) if agg["played"] else 0

    def _latest_elo(surface: Optional[str]) -> Optional[float]:
        q = db.query(CompetitorEloHistory).filter(
            CompetitorEloHistory.competitor_id == competitor_id
        )
        if surface is None:
            q = q.filter(CompetitorEloHistory.surface.is_(None))
        else:
            q = q.filter(CompetitorEloHistory.surface == surface)
        row = q.order_by(CompetitorEloHistory.calculated_at.desc()).first()
        return float(row.elo_after) if row and row.elo_after is not None else None

    return {
        "surfaces": surfaces,
        "elo_overall": _latest_elo(None),
        "elo_by_surface": {s: _latest_elo(s) for s in ("hard", "clay", "grass")},
    }


def get_match_surface_stats(db: Session, external_match_id: str) -> Optional[Dict[str, Any]]:
    """Surface career stats for both competitors of a match (by external id).

    Powers the frontend "Rendimiento por superficie" section: per player, the
    career W-L record and win rate on hard/clay/grass plus current Elo ratings,
    so users can judge how strong each player is on the match's surface.
    """
    match = db.query(Match).filter(Match.external_id == external_match_id).first()
    if not match:
        return None

    def _side_order(mc: MatchCompetitor) -> int:
        return 0 if mc.side in ("player1", "home") else 1

    players = []
    for mc in sorted(match.competitors, key=_side_order):
        comp = mc.competitor
        if not comp:
            continue
        career = compute_surface_career(db, mc.competitor_id)
        players.append(
            {
                "name": comp.name,
                "side": mc.side,
                "surfaces": career["surfaces"],
                "eloOverall": career["elo_overall"],
                "eloBySurface": career["elo_by_surface"],
            }
        )

    return {
        "matchId": external_match_id,
        "surface": normalize_surface((match.extra_data or {}).get("surface")),
        "players": players,
    }


def compute_tournament_load(db: Session, external_match_id: str) -> Optional[Dict[str, Any]]:
    """Tournament-to-date physical load for both players of an (upcoming) match.

    For each competitor of the given match, accumulates their finished matches
    in the SAME tournament (same league, last 10 days, strictly before this
    match's date): matches played, sets won/lost (from FULL_TIME scores),
    games won/lost and points won/lost (from per-set data stored in
    extra_data['score_stats'] when available). Powers the frontend "Carga en
    el torneo" section so users can see how tired each player arrives to
    their next match.
    """
    from datetime import timedelta

    from src.application.feature_service import _scores_for_side

    match = db.query(Match).filter(Match.external_id == external_match_id).first()
    if not match or not match.league_id or not match.match_date:
        return None

    def _side_order(mc: MatchCompetitor) -> int:
        return 0 if mc.side in ("player1", "home") else 1

    # Finished matches in this tournament before the given match
    window_start = match.match_date - timedelta(days=10)
    tournament_matches = (
        db.query(Match)
        .filter(Match.league_id == match.league_id)
        .filter(Match.sport_id == match.sport_id)
        .filter(Match.status == "FINISHED")
        .filter(Match.match_date >= window_start)
        .filter(Match.match_date < match.match_date)
        .all()
    )
    if not tournament_matches:
        tournament_matches = []

    t_ids = [m.id for m in tournament_matches]
    meta_by_id = {m.id: (m.extra_data or {}) for m in tournament_matches}

    # Competitor links for those matches + FULL_TIME scores
    links = (
        db.query(MatchCompetitor)
        .filter(MatchCompetitor.match_id.in_(t_ids))
        .all()
        if t_ids
        else []
    )
    scores = (
        db.query(MatchScore)
        .filter(MatchScore.match_id.in_(t_ids), MatchScore.period == "FULL_TIME")
        .all()
        if t_ids
        else []
    )
    score_by_match = {s.match_id: s for s in scores}
    links_by_competitor: Dict[Any, List[MatchCompetitor]] = {}
    for link in links:
        links_by_competitor.setdefault(link.competitor_id, []).append(link)

    players = []
    for mc in sorted(match.competitors, key=_side_order):
        comp = mc.competitor
        if not comp:
            continue
        matches_played = 0
        sets_won = 0
        sets_lost = 0
        games_won = 0
        games_lost = 0
        games_matches = 0
        points_won = 0
        points_lost = 0
        points_matches = 0

        for link in links_by_competitor.get(mc.competitor_id, []):
            score = score_by_match.get(link.match_id)
            if not score:
                continue
            matches_played += 1
            my_sets, opp_sets = _scores_for_side(link, score)
            sets_won += my_sets
            sets_lost += opp_sets

            # Per-set games/points from stored score_stats (when available)
            stats = (meta_by_id.get(link.match_id) or {}).get("score_stats") or {}
            set_rows = stats.get("sets") or []
            point_rows = stats.get("points") or []
            if set_rows or point_rows:
                is_home = link.side in ("player1", "home")
            if set_rows:
                games_matches += 1
                for row in set_rows:
                    try:
                        p1 = int(row.get("p1") or 0)
                        p2 = int(row.get("p2") or 0)
                    except (TypeError, ValueError):
                        continue
                    if is_home:
                        games_won += p1
                        games_lost += p2
                    else:
                        games_won += p2
                        games_lost += p1
            if point_rows:
                points_matches += 1
                for row in point_rows:
                    try:
                        p1 = int(row.get("p1") or 0)
                        p2 = int(row.get("p2") or 0)
                    except (TypeError, ValueError):
                        continue
                    if p1 + p2 == 0:
                        continue
                    if is_home:
                        points_won += p1
                        points_lost += p2
                    else:
                        points_won += p2
                        points_lost += p1

        total_games = games_won + games_lost
        has_games = games_matches > 0
        # Load level from total games played in the tournament (a player
        # reaching the final typically accumulates 60-90 games).
        if total_games < 25:
            load_level = "leve"
        elif total_games < 50:
            load_level = "media"
        else:
            load_level = "alta"

        players.append(
            {
                "name": comp.name,
                "side": mc.side,
                "matchesPlayed": matches_played,
                "setsWon": sets_won,
                "setsLost": sets_lost,
                "gamesWon": games_won if has_games else None,
                "gamesLost": games_lost if has_games else None,
                "gamesMatches": games_matches,
                "pointsWon": points_won if points_matches else None,
                "pointsLost": points_lost if points_matches else None,
                "totalGames": total_games if has_games else None,
                "loadLevel": load_level if has_games else None,
                "loadPct": min(100, round(total_games / 70 * 100)) if has_games else None,
            }
        )

    return {
        "matchId": external_match_id,
        "tournament": match.league.name if match.league else None,
        "players": players,
    }


def compute_surface_load(
    db: Session, external_match_id: str, days: int = 30
) -> Optional[Dict[str, Any]]:
    """Recent physical effort per surface and rest time for both players.

    For each competitor of the given match, accumulates their finished matches
    in the last `days` days strictly before this match's date (any tournament),
    grouped by normalized surface: matches played and games won/lost (from
    per-set scores in extra_data['score_stats'] when available). Also computes
    the rest time between their last finished match and this one.

    Powers the frontend "Esfuerzo por superficie y descanso" section so users
    can see how much recent workload each player carries on each surface and
    how fresh they arrive to the match.
    """
    from datetime import timedelta

    match = db.query(Match).filter(Match.external_id == external_match_id).first()
    if not match or not match.match_date:
        return None

    def _side_order(mc: MatchCompetitor) -> int:
        return 0 if mc.side in ("player1", "home") else 1

    competitor_ids = [mc.competitor_id for mc in match.competitors if mc.competitor_id]
    window_start = match.match_date - timedelta(days=days)

    rows: List[Any] = []
    if competitor_ids:
        rows = (
            db.query(Match, MatchCompetitor, MatchScore)
            .join(MatchCompetitor, Match.id == MatchCompetitor.match_id)
            .join(
                MatchScore,
                (Match.id == MatchScore.match_id) & (MatchScore.period == "FULL_TIME"),
            )
            .filter(Match.sport_id == match.sport_id)
            .filter(Match.status == "FINISHED")
            .filter(MatchCompetitor.competitor_id.in_(competitor_ids))
            .filter(Match.match_date >= window_start)
            .filter(Match.match_date < match.match_date)
            .all()
        )

    rows_by_competitor: Dict[Any, List[Any]] = {}
    for m, mc, score in rows:
        rows_by_competitor.setdefault(mc.competitor_id, []).append((m, mc, score))

    players = []
    for mc in sorted(match.competitors, key=_side_order):
        comp = mc.competitor
        if not comp:
            continue

        surfaces: Dict[str, Dict[str, Any]] = {}
        for m, link, score in rows_by_competitor.get(mc.competitor_id, []):
            surface = normalize_surface((m.extra_data or {}).get("surface"))
            if not surface:
                continue
            agg = surfaces.setdefault(
                surface,
                {"matchesPlayed": 0, "gamesWon": 0, "gamesLost": 0, "gamesMatches": 0},
            )
            agg["matchesPlayed"] += 1
            stats = (m.extra_data or {}).get("score_stats") or {}
            set_rows = stats.get("sets") or []
            if not set_rows:
                continue
            agg["gamesMatches"] += 1
            is_home = link.side in ("player1", "home")
            for row in set_rows:
                try:
                    p1 = int(row.get("p1") or 0)
                    p2 = int(row.get("p2") or 0)
                except (TypeError, ValueError):
                    continue
                if is_home:
                    agg["gamesWon"] += p1
                    agg["gamesLost"] += p2
                else:
                    agg["gamesWon"] += p2
                    agg["gamesLost"] += p1

        for agg in surfaces.values():
            has_games = agg["gamesMatches"] > 0
            agg["totalGames"] = agg["gamesWon"] + agg["gamesLost"] if has_games else None
            if not has_games:
                agg["gamesWon"] = None
                agg["gamesLost"] = None
            del agg["gamesMatches"]

        last_match = (
            db.query(Match)
            .join(MatchCompetitor, Match.id == MatchCompetitor.match_id)
            .filter(Match.sport_id == match.sport_id)
            .filter(Match.status == "FINISHED")
            .filter(MatchCompetitor.competitor_id == mc.competitor_id)
            .filter(Match.match_date < match.match_date)
            .order_by(Match.match_date.desc())
            .first()
        )

        rest_days = None
        last_match_date = None
        last_match_surface = None
        last_match_tournament = None
        if last_match and last_match.match_date:
            last_match_date = last_match.match_date.date().isoformat()
            rest_days = (match.match_date.date() - last_match.match_date.date()).days
            last_match_surface = normalize_surface((last_match.extra_data or {}).get("surface"))
            last_match_tournament = last_match.league.name if last_match.league else None

        players.append(
            {
                "name": comp.name,
                "side": mc.side,
                "restDays": rest_days,
                "lastMatchDate": last_match_date,
                "lastMatchSurface": last_match_surface,
                "lastMatchTournament": last_match_tournament,
                "surfaces": surfaces,
                "totalGames": sum(
                    agg["totalGames"] or 0 for agg in surfaces.values()
                ),
                "totalMatches": sum(agg["matchesPlayed"] for agg in surfaces.values()),
            }
        )

    return {
        "matchId": external_match_id,
        "windowDays": days,
        "surface": normalize_surface((match.extra_data or {}).get("surface")),
        "players": players,
    }


def aggregate_serve_stats(
    match_links: List[Tuple[Match, MatchCompetitor]], max_matches: int = 20
) -> Dict[str, Any]:
    """Aggregate serve/return and tiebreak stats from stored score_stats.

    match_links: (Match, MatchCompetitor) pairs of finished matches, most
    recent first. Caps at `max_matches` matches WITH serve data. Percentages
    are 0-1 floats or None when there is no data. Tiebreaks are counted from
    per-set games (7-6 sets) over the same window.
    """
    sg_won = sg_total = 0
    rg_won = rg_total = 0
    fs_won = fs_total = 0
    ss_total = serve_pts_total = 0
    serve_matches = 0
    tb_played = tb_won = 0

    for m, link in match_links:
        if serve_matches >= max_matches:
            break
        stats = (m.extra_data or {}).get("score_stats") or {}
        is_home = link.side in ("player1", "home")

        for row in stats.get("sets") or []:
            try:
                p1_games = int(row.get("p1") or 0)
                p2_games = int(row.get("p2") or 0)
            except (TypeError, ValueError):
                continue
            if {p1_games, p2_games} == {7, 6}:
                tb_played += 1
                if (p1_games == 7) == is_home:
                    tb_won += 1

        serve = stats.get("serve") or {}
        mine = serve.get("home" if is_home else "away") or {}
        if not mine:
            continue
        try:
            sgw = int(mine.get("serveGamesWon") or 0)
            sgt = int(mine.get("serveGamesTotal") or 0)
            rgw = int(mine.get("returnGamesWon") or 0)
            rgt = int(mine.get("returnGamesTotal") or 0)
            fw = int(mine.get("firstServeWon") or 0)
            ft = int(mine.get("firstServeTotal") or 0)
            st = int(mine.get("secondServeTotal") or 0)
            spt = int(mine.get("servePtsTotal") or 0)
        except (TypeError, ValueError):
            continue
        if not sgt:
            continue
        serve_matches += 1
        sg_won += sgw
        sg_total += sgt
        rg_won += rgw
        rg_total += rgt
        fs_won += fw
        fs_total += ft
        ss_total += st
        serve_pts_total += spt

    return {
        "serveMatches": serve_matches,
        "holdPct": round(sg_won / sg_total, 3) if sg_total else None,
        "breakPct": round(rg_won / rg_total, 3) if rg_total else None,
        "firstServePct": (
            round((serve_pts_total - ss_total) / serve_pts_total, 3)
            if serve_pts_total
            else None
        ),
        "firstServeWonPct": round(fs_won / fs_total, 3) if fs_total else None,
        "tiebreaksPlayed": tb_played,
        "tiebreaksWon": tb_won,
    }


def compute_match_serve_stats(db: Session, external_match_id: str) -> Optional[Dict[str, Any]]:
    """Serve/return profile for both players of a tennis match.

    Per player: overall hold/break %, first-serve % and first-serve points
    won %, tiebreak record (last 20 matches with stats) plus hold/break %
    per surface. Powers the frontend "Saque, resto y tiebreaks" section.
    """
    match = db.query(Match).filter(Match.external_id == external_match_id).first()
    if not match or not match.match_date:
        return None

    def _side_order(mc: MatchCompetitor) -> int:
        return 0 if mc.side in ("player1", "home") else 1

    players = []
    for mc in sorted(match.competitors, key=_side_order):
        comp = mc.competitor
        if not comp:
            continue
        rows = (
            db.query(Match, MatchCompetitor)
            .join(MatchCompetitor, Match.id == MatchCompetitor.match_id)
            .filter(MatchCompetitor.competitor_id == mc.competitor_id)
            .filter(Match.status == "FINISHED")
            .filter(Match.match_date < match.match_date)
            .filter(Match.extra_data["score_stats"].isnot(None))
            .order_by(Match.match_date.desc())
            .limit(60)
            .all()
        )
        overall = aggregate_serve_stats(rows, max_matches=20)
        by_surface: Dict[str, Any] = {}
        for surface in ("hard", "clay", "grass"):
            surface_rows = [
                (m, link)
                for m, link in rows
                if normalize_surface((m.extra_data or {}).get("surface")) == surface
            ]
            agg = aggregate_serve_stats(surface_rows, max_matches=20)
            if agg["serveMatches"]:
                by_surface[surface] = {
                    "holdPct": agg["holdPct"],
                    "breakPct": agg["breakPct"],
                    "serveMatches": agg["serveMatches"],
                }
        players.append(
            {
                "name": comp.name,
                "side": mc.side,
                "overall": overall,
                "bySurface": by_surface,
            }
        )

    return {
        "matchId": external_match_id,
        "surface": normalize_surface((match.extra_data or {}).get("surface")),
        "players": players,
    }


def compute_player_set_stats(db: Session, target_date) -> Dict[str, Any]:
    """Average games and points per set by surface for players with a match.

    For every competitor of tennis matches scheduled on the given date,
    aggregates all their finished matches that have per-set scores stored in
    extra_data['score_stats']['sets'] (and points in ['points'] when stored),
    grouped by normalized surface: sets played, games/points won-lost and
    averages per set.

    Powers the Dashboard "Games y puntos por set" section.
    """
    from datetime import timedelta

    from src.timezone import BOGOTA_TZ

    day_start = datetime.combine(target_date, datetime.min.time(), tzinfo=BOGOTA_TZ)
    day_end = day_start + timedelta(days=1)

    todays_matches = (
        db.query(Match)
        .join(Sport, Match.sport_id == Sport.id)
        .filter(Sport.code == "tennis")
        .filter(Match.status != "CANCELLED")
        .filter(Match.match_date >= day_start)
        .filter(Match.match_date < day_end)
        .order_by(Match.match_date.asc())
        .all()
    )
    if not todays_matches:
        return {"date": target_date.isoformat(), "players": []}

    def _side_order(mc: MatchCompetitor) -> int:
        return 0 if mc.side in ("player1", "home") else 1

    players_meta: List[Dict[str, Any]] = []
    seen: Set[Any] = set()
    for m in todays_matches:
        surface = normalize_surface((m.extra_data or {}).get("surface"))
        for mc in sorted(m.competitors, key=_side_order):
            if not mc.competitor or mc.competitor_id in seen:
                continue
            seen.add(mc.competitor_id)
            players_meta.append(
                {
                    "competitor_id": mc.competitor_id,
                    "name": mc.competitor.name,
                    "matchId": m.external_id,
                    "surface": surface,
                }
            )

    if not players_meta:
        return {"date": target_date.isoformat(), "players": []}

    rows = (
        db.query(Match, MatchCompetitor)
        .join(MatchCompetitor, Match.id == MatchCompetitor.match_id)
        .filter(Match.status == "FINISHED")
        .filter(MatchCompetitor.competitor_id.in_([p["competitor_id"] for p in players_meta]))
        .filter(Match.extra_data["score_stats"].isnot(None))
        .all()
    )

    stats_by_player: Dict[Any, Dict[str, Any]] = {}
    for m, link in rows:
        surface = normalize_surface((m.extra_data or {}).get("surface"))
        if not surface:
            continue
        stats = (m.extra_data or {}).get("score_stats") or {}
        set_rows = stats.get("sets") or []
        if not set_rows:
            continue
        point_rows = stats.get("points") or []
        is_home = link.side in ("player1", "home")
        surfaces = stats_by_player.setdefault(link.competitor_id, {})
        agg = surfaces.setdefault(
            surface,
            {"setsPlayed": 0, "gamesWon": 0, "gamesLost": 0,
             "pointsWon": 0, "pointsLost": 0, "pointsSets": 0},
        )
        for row in set_rows:
            try:
                p1_games = int(row.get("p1") or 0)
                p2_games = int(row.get("p2") or 0)
            except (TypeError, ValueError):
                continue
            if p1_games + p2_games == 0:
                continue
            agg["setsPlayed"] += 1
            if is_home:
                agg["gamesWon"] += p1_games
                agg["gamesLost"] += p2_games
            else:
                agg["gamesWon"] += p2_games
                agg["gamesLost"] += p1_games
        for row in point_rows:
            try:
                p1_points = int(row.get("p1") or 0)
                p2_points = int(row.get("p2") or 0)
            except (TypeError, ValueError):
                continue
            if p1_points + p2_points == 0:
                continue
            agg["pointsSets"] += 1
            if is_home:
                agg["pointsWon"] += p1_points
                agg["pointsLost"] += p2_points
            else:
                agg["pointsWon"] += p2_points
                agg["pointsLost"] += p1_points

    players = []
    for meta in players_meta:
        surfaces = stats_by_player.get(meta["competitor_id"], {})
        out_surfaces: Dict[str, Any] = {}
        total_sets = 0
        for surface, agg in surfaces.items():
            n = agg["setsPlayed"]
            if not n:
                continue
            total_sets += n
            points_sets = agg["pointsSets"]
            out_surfaces[surface] = {
                "setsPlayed": n,
                "gamesWon": agg["gamesWon"],
                "gamesLost": agg["gamesLost"],
                "avgGamesWon": round(agg["gamesWon"] / n, 1),
                "avgGamesLost": round(agg["gamesLost"] / n, 1),
                "avgTotal": round((agg["gamesWon"] + agg["gamesLost"]) / n, 1),
                "pointsWon": agg["pointsWon"] if points_sets else None,
                "pointsLost": agg["pointsLost"] if points_sets else None,
                "pointsSets": points_sets or None,
                "avgPointsWon": round(agg["pointsWon"] / points_sets, 1) if points_sets else None,
                "avgPointsLost": round(agg["pointsLost"] / points_sets, 1) if points_sets else None,
            }
        players.append(
            {
                "name": meta["name"],
                "matchId": meta["matchId"],
                "matchSurface": meta["surface"],
                "surfaces": out_surfaces,
                "totalSets": total_sets,
            }
        )

    players.sort(key=lambda p: p["totalSets"], reverse=True)
    return {"date": target_date.isoformat(), "players": players}


# ---------------------------------------------------------------------------
# Prediction reliability by player and surface
# ---------------------------------------------------------------------------
# Market display order / short Spanish labels for the UI.
_MARKET_LABELS = {
    "Match Winner": "Ganador del partido",
    "Set 1 Winner": "Ganador del primer set",
    "Total Sets": "Total de sets (over/under)",
    "Exact Set Score": "Marcador exacto de sets",
    "Total Aces": "Total de aces (over/under)",
}


def compute_prediction_reliability(
    db: Session,
    player: Optional[str] = None,
    surface: Optional[str] = None,
    min_sample: int = 4,
) -> Dict[str, Any]:
    """How reliable each prediction market has been, per tennis player and surface.

    For every validated tennis prediction, the match is attributed to BOTH of
    its competitors (the market is a property of the match, e.g. "does this
    match reach a 3rd set"). Results are grouped by (player, surface, market)
    and the hit rate is reported alongside the sample size. ``best`` / ``worst``
    per (player, surface) are only filled when the top/bottom market has at
    least ``min_sample`` validated predictions; otherwise they are ``None`` and
    the caller should show "insufficient sample".
    """
    from sqlalchemy import Integer, cast, func

    q = (
        db.query(
            Competitor.name.label("player"),
            Match.extra_data["surface"].astext.label("surface_raw"),
            Prediction.market.label("market"),
            func.count().label("n"),
            func.coalesce(func.sum(cast(PredictionResult.is_successful, Integer)), 0).label("hits"),
        )
        .select_from(PredictionResult)
        .join(Prediction, Prediction.id == PredictionResult.prediction_id)
        .join(Match, Match.id == Prediction.match_id)
        .join(Sport, Sport.id == Match.sport_id)
        .join(MatchCompetitor, MatchCompetitor.match_id == Match.id)
        .join(Competitor, Competitor.id == MatchCompetitor.competitor_id)
        .filter(Sport.code == "tennis")
        .filter(PredictionResult.is_successful.isnot(None))
        .filter(MatchCompetitor.side.in_(["player1", "player2"]))
        .group_by(Competitor.name, Match.extra_data["surface"].astext, Prediction.market)
    )
    if player:
        q = q.filter(func.lower(Competitor.name).like(f"%{player.strip().lower()}%"))

    # players[name][surface][market] = [n, hits]
    players: Dict[str, Dict[str, Dict[str, list]]] = {}
    overall: Dict[str, Dict[str, list]] = {}
    for name, surf_raw, market, n, hits in q.all():
        surf = normalize_surface(surf_raw)
        if not surf or (surface and surf != surface):
            continue
        pm = players.setdefault(name, {}).setdefault(surf, {})
        cell = pm.setdefault(market, [0, 0])
        cell[0] += int(n)
        cell[1] += int(hits)
        oc = overall.setdefault(surf, {}).setdefault(market, [0, 0])
        oc[0] += int(n)
        oc[1] += int(hits)

    def _pack(surface_map: Dict[str, Dict[str, list]]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for surf, markets in surface_map.items():
            rows = [
                {
                    "market": m,
                    "label": _MARKET_LABELS.get(m, m),
                    "n": v[0],
                    "hits": v[1],
                    "hitRate": round(100.0 * v[1] / v[0], 1) if v[0] else 0.0,
                }
                for m, v in markets.items()
            ]
            rows.sort(key=lambda r: (-r["hitRate"], -r["n"]))
            eligible = [r for r in rows if r["n"] >= min_sample]
            out[surf] = {
                "markets": rows,
                "best": eligible[0] if eligible else None,
                "worst": eligible[-1] if len(eligible) >= 2 else None,
                "sampleTotal": sum(r["n"] for r in rows),
            }
        return out

    player_blocks = [
        {"player": name, "surfaces": _pack(surface_map)}
        for name, surface_map in players.items()
    ]
    player_blocks.sort(
        key=lambda p: sum(s["sampleTotal"] for s in p["surfaces"].values()),
        reverse=True,
    )

    return {
        "generatedAt": datetime.utcnow().isoformat() + "Z",
        "minSample": min_sample,
        "players": player_blocks,
        "overall": _pack(overall),
    }
