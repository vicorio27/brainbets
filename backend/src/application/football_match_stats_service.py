"""Per-match team statistics for La Liga and the Premier League (shots, possession, xG...).

API-Football serves them one call per match (`fixtures/statistics`), from 2022 on. They are kept in
`matches.extra_data['team_stats'] = {"home": {...}, "away": {...}}` with the API's own names
normalised to snake_case numbers, plus `af_fixture` (the API's fixture id) so the match is never
looked up twice. Nothing in the models reads them yet: they feed the football card ("how are they
playing") and, later, the xG-based checks.

Historical matches (football-data files) carry no fixture id, so each season's fixture list is
fetched once (1 call per league-season) and matched by date and team names.
"""
import logging
import re
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.application.football_collect_service import LEAGUES, Provider, season_code, team_name
from src.domain.models import MatchCompetitor, Match, Sport
from src.timezone import to_bogota

FIRST_SEASON = 2022          # the API's statistics start here
LAST_SEASON = 2026


def slug(kind: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (kind or "").lower()).strip("_")


def number(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace("%", "").strip())
    except ValueError:
        return None


def parse_stats(response: List[Dict[str, Any]], home_id: Optional[int], away_id: Optional[int]) -> Optional[Dict[str, Dict[str, float]]]:
    """`fixtures/statistics` response -> {home: {...}, away: {...}}. None when the API has nothing."""
    if not response or len(response) < 2:
        return None
    out: Dict[str, Dict[str, float]] = {}
    for i, side_resp in enumerate(response[:2]):
        tid = (side_resp.get("team") or {}).get("id")
        if home_id and tid == home_id:
            side = "home"
        elif away_id and tid == away_id:
            side = "away"
        else:
            side = "home" if i == 0 else "away"
        vals = {}
        for s in side_resp.get("statistics") or []:
            n = number(s.get("value"))
            if n is not None:
                vals[slug(s.get("type"))] = n
        out[side] = vals
    if set(out) != {"home", "away"} or not (out["home"] or out["away"]):
        return None
    return out


def _fixture_index(fixtures: List[Dict[str, Any]]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    """(day, home, away) in our names -> {id, home_id, away_id}. Day is the UTC date of the fixture."""
    idx: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for fx in fixtures:
        f = fx.get("fixture") or {}
        t = fx.get("teams") or {}
        day = str(f.get("date") or "")[:10]
        key = (day, team_name((t.get("home") or {}).get("name", "")), team_name((t.get("away") or {}).get("name", "")))
        idx[key] = {"id": f.get("id"), "home_id": (t.get("home") or {}).get("id"), "away_id": (t.get("away") or {}).get("id")}
    return idx


def _names(db: Session, match: Match) -> Tuple[Optional[str], Optional[str]]:
    sides = {mc.side: mc.competitor.name for mc in db.query(MatchCompetitor).filter(MatchCompetitor.match_id == match.id).all()}
    return sides.get("home"), sides.get("away")


def find_fixture(idx: Dict[Tuple[str, str, str], Dict[str, Any]], day, home: str, away: str) -> Optional[Dict[str, Any]]:
    for delta in (0, -1, 1):
        d = (day + timedelta(days=delta)).strftime("%Y-%m-%d")
        hit = idx.get((d, home, away))
        if hit:
            return hit
    return None


def run(db: Session, storage: str, max_calls: int = 5000, seasons: Optional[List[int]] = None) -> Dict[str, Any]:
    """Download the statistics of every finished PL/PD match that has none yet."""
    key = __import__("os").environ.get("API_FOOTBALL_KEY", "")
    if not key:
        return {"error": "no API_FOOTBALL_KEY"}
    prov = Provider(key, storage)
    sport = db.query(Sport).filter(Sport.code == "football").first()
    if not sport:
        return {"error": "no football"}

    idx: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    by_id: Dict[int, Dict[str, Any]] = {}
    for year in seasons or list(range(FIRST_SEASON, LAST_SEASON + 1)):
        for league in LEAGUES:
            d = prov.get("fixtures", {"league": league, "season": year})
            fxs = (d or {}).get("response") or []
            idx.update(_fixture_index(fxs))
            for fx in fxs:
                t = fx.get("teams") or {}
                fid = (fx.get("fixture") or {}).get("id")
                if fid:
                    by_id[fid] = {"id": fid, "home_id": (t.get("home") or {}).get("id"), "away_id": (t.get("away") or {}).get("id")}

    codes = [season_code(y) for y in (seasons or range(FIRST_SEASON, LAST_SEASON + 1))]
    matches = (db.query(Match).filter(Match.sport_id == sport.id, Match.status == "FINISHED", Match.season.in_(codes))
               .order_by(Match.match_date).all())
    done = unmatched = empty = skipped = 0
    for m in matches:
        extra = m.extra_data or {}
        if "team_stats" in extra:
            skipped += 1
            continue
        fx = None
        ext = m.external_id or ""
        if ext.startswith("FOOTBALL-AF-"):
            try:
                fx = by_id.get(int(ext.split("-")[-1])) or {"id": int(ext.split("-")[-1]), "home_id": None, "away_id": None}
            except ValueError:
                fx = None
        else:
            home, away = _names(db, m)
            if home and away:
                fx = find_fixture(idx, to_bogota(m.match_date), home, away)
        if not fx or not fx.get("id"):
            unmatched += 1
            continue
        if prov.used >= max_calls:
            break
        d = prov.get("fixtures/statistics", {"fixture": fx["id"]})
        if d is None:
            break                                  # cap or a hard error: stop, the next run resumes
        stats = parse_stats(d.get("response") or [], fx.get("home_id"), fx.get("away_id"))
        if not stats:
            empty += 1
            m.extra_data = {**extra, "af_fixture": fx["id"], "team_stats": {}}      # looked up: nothing there
            db.commit()
            continue
        m.extra_data = {**extra, "af_fixture": fx["id"], "team_stats": stats}       # new dict (gotcha #43)
        done += 1
        if done % 100 == 0:
            db.commit()
            logging.warning("[FOOTBALL-STATS] %d downloaded", done)
    db.commit()
    return {"downloaded": done, "alreadyHad": skipped, "unmatched": unmatched, "empty": empty, "calls": prov.used}
