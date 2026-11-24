"""Football match simulation: how the next match should go, from what we measured.

For a fixture it assembles, with numbers only and always "from earlier matches":
- goals: expected goals of each side (the Poisson model), the 1X2, over/under and both-teams-score
  probabilities and the likeliest scorelines (exact, from the Poisson grid);
- goal minutes: when each side scores and concedes, by 15-minute band, from each team's recent matches
  shrunk toward the league's own shape (`goals` events, see `football_events_service`);
- corners: expected corners of each side and the chance of going over a few lines (the corners model
  frozen for the corners lab);
- H2H: the recent meetings, as information (adding it to the model did not improve any forecast).

It is a description of the likeliest match, not a signal against the price: none of this has been
measured against bookmaker odds yet.
"""
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.stats import nbinom, poisson
from sqlalchemy.orm import Session

from src.application import football_corners_lab_service as corners_lab
from src.application.poisson_service import expected_goals_for_fixture
from src.domain.models import Match, MatchCompetitor, MatchScore
from src.timezone import to_bogota

BANDS: List[Tuple[int, int]] = [(0, 15), (16, 30), (31, 45), (46, 60), (61, 75), (76, 130)]
BAND_LABELS = ["1-15", "16-30", "31-45", "46-60", "61-75", "76-90+"]
TEAM_MATCHES = 40            # recent matches that build a team's minute profile
SHAPE_PSEUDO = 25.0          # pseudo-goals of league shape mixed into a team's profile
H2H_MAX = 6
MAX_GOALS = 10


def band_of(minute: int) -> int:
    for i, (lo, hi) in enumerate(BANDS):
        if lo <= minute <= hi:
            return i
    return len(BANDS) - 1


def band_counts(goals: List[Dict[str, Any]], side: str) -> List[int]:
    """Goals by band scored by `side` (home|away) in one match."""
    out = [0] * len(BANDS)
    for g in goals or []:
        if g.get("s") == side:
            out[band_of(int(g.get("m", 0)))] += 1
    return out


def shares(counts: List[float], shape: List[float], pseudo: float = SHAPE_PSEUDO) -> List[float]:
    """Share of goals per band: the team's counts shrunk toward the league shape."""
    total = sum(counts) + pseudo
    return [(c + pseudo * s) / total for c, s in zip(counts, shape)]


def mix(scoring: List[float], conceding: List[float]) -> List[float]:
    """When a team scores against a given rival: average of its own scoring shape and the rival's conceding shape."""
    m = [(a + b) / 2 for a, b in zip(scoring, conceding)]
    t = sum(m)
    return [x / t for x in m]


def score_grid(lh: float, la: float) -> np.ndarray:
    k = np.arange(0, MAX_GOALS + 1)
    grid = np.outer(poisson.pmf(k, lh), poisson.pmf(k, la))
    return grid / grid.sum()


def goal_markets(lh: float, la: float) -> Dict[str, Any]:
    grid = score_grid(lh, la)
    k = np.arange(0, MAX_GOALS + 1)
    tot = np.add.outer(k, k)
    best = sorted(((float(grid[i, j]), i, j) for i in range(5) for j in range(5)), reverse=True)[:5]
    return {
        "home": round(float(np.tril(grid, -1).sum()), 4), "draw": round(float(np.trace(grid)), 4),
        "away": round(float(np.triu(grid, 1).sum()), 4),
        "over": {str(x): round(float(grid[tot > x].sum()), 4) for x in (0.5, 1.5, 2.5, 3.5)},
        "btts": round(float(grid[1:, 1:].sum()), 4),
        "scorelines": [{"score": f"{i}-{j}", "p": round(p, 4)} for p, i, j in best],
    }


def minute_view(lh: float, la: float, h_sc, h_co, a_sc, a_co) -> List[Dict[str, Any]]:
    """Expected goals of each side in each band, and the chance that a goal falls in the band."""
    hm, am = mix(h_sc, a_co), mix(a_sc, h_co)
    out = []
    for i, label in enumerate(BAND_LABELS):
        eh, ea = lh * hm[i], la * am[i]
        out.append({"band": label, "home": round(eh, 3), "away": round(ea, 3),
                    "anyGoal": round(1 - float(np.exp(-(eh + ea))), 3)})
    return out


def _team_matches(db: Session, competitor_id, before, limit: int) -> List[Tuple[Match, str]]:
    rows = (db.query(Match, MatchCompetitor.side).join(MatchCompetitor, MatchCompetitor.match_id == Match.id)
            .filter(MatchCompetitor.competitor_id == competitor_id, Match.status == "FINISHED", Match.match_date < before)
            .order_by(Match.match_date.desc()).limit(limit).all())
    return [(m, side) for m, side in rows]


def _profile(rows: List[Tuple[Match, str]]) -> Tuple[List[int], List[int], int]:
    scored, conceded, n = [0] * len(BANDS), [0] * len(BANDS), 0
    for m, side in rows:
        goals = (m.extra_data or {}).get("goals")
        if goals is None:
            continue
        other = "away" if side == "home" else "home"
        for i, (a, b) in enumerate(zip(band_counts(goals, side), band_counts(goals, other))):
            scored[i] += a
            conceded[i] += b
        n += 1
    return scored, conceded, n


def _league_shape(db: Session, league_id, before, limit: int = 600) -> List[float]:
    counts = [0] * len(BANDS)
    q = (db.query(Match).filter(Match.league_id == league_id, Match.status == "FINISHED", Match.match_date < before)
         .order_by(Match.match_date.desc()).limit(limit))
    for m in q:
        goals = (m.extra_data or {}).get("goals")
        if not goals:
            continue
        for g in goals:
            counts[band_of(int(g.get("m", 0)))] += 1
    t = sum(counts)
    return [c / t for c in counts] if t >= 100 else [1 / len(BANDS)] * len(BANDS)


def _corner_pairs(rows: List[Tuple[Match, str]]) -> List[Tuple[float, float]]:
    """(for, against) corners of a team, oldest first."""
    out = []
    for m, side in reversed(rows):
        ts = (m.extra_data or {}).get("team_stats") or {}
        a, b = (ts.get("home") or {}).get("corner_kicks"), (ts.get("away") or {}).get("corner_kicks")
        if a is None or b is None:
            continue
        out.append((float(a), float(b)) if side == "home" else (float(b), float(a)))
    return out


def _league_corner_means(db: Session, league_id, before, limit: int = 600) -> Optional[Tuple[float, float]]:
    h = a = n = 0
    q = (db.query(Match).filter(Match.league_id == league_id, Match.status == "FINISHED", Match.match_date < before,
                                Match.extra_data["team_stats"].isnot(None))
         .order_by(Match.match_date.desc()).limit(limit))
    for m in q:
        ts = (m.extra_data or {}).get("team_stats") or {}
        ch, ca = (ts.get("home") or {}).get("corner_kicks"), (ts.get("away") or {}).get("corner_kicks")
        if ch is not None and ca is not None:
            h, a, n = h + ch, a + ca, n + 1
    return (h / n, a / n) if n >= 50 else None


def corners_view(db: Session, m: Match, home_id, away_id) -> Optional[Dict[str, Any]]:
    lg = _league_corner_means(db, m.league_id, m.match_date)
    if lg is None:
        return None
    hr = _team_matches(db, home_id, m.match_date, corners_lab.WINDOW)
    ar = _team_matches(db, away_id, m.match_date, corners_lab.WINDOW)
    split = corners_lab.corners_split(_corner_pairs(hr), _corner_pairs(ar), lg[0], lg[1])
    if split is None:
        return None
    total = split[0] + split[1]
    return {"home": round(split[0], 2), "away": round(split[1], 2), "total": round(total, 2),
            "over": {str(x): round(corners_lab.p_over(total, x), 3) for x in (8.5, 9.5, 10.5, 11.5)}}


def h2h_view(db: Session, m: Match, home_id, away_id) -> Dict[str, Any]:
    ids = {str(home_id), str(away_id)}
    cand = (db.query(Match).join(MatchCompetitor, MatchCompetitor.match_id == Match.id)
            .filter(MatchCompetitor.competitor_id == home_id, Match.status == "FINISHED", Match.match_date < m.match_date)
            .order_by(Match.match_date.desc()).limit(400).all())
    meetings = []
    for x in cand:
        sides = {mc.side: str(mc.competitor_id) for mc in x.competitors}
        if set(sides.values()) != ids:
            continue
        sc = next((s for s in x.scores if s.period == "FULL_TIME"), None)
        if not sc or sc.home_score is None:
            continue
        names = {mc.side: mc.competitor.name for mc in x.competitors}
        ts = (x.extra_data or {}).get("team_stats") or {}
        co = [(ts.get(s) or {}).get("corner_kicks") for s in ("home", "away")]
        meetings.append({"date": to_bogota(x.match_date).strftime("%Y-%m-%d"), "home": names.get("home"), "away": names.get("away"),
                         "score": f"{sc.home_score}-{sc.away_score}", "homeId": sides.get("home"),
                         "goals": sc.home_score + sc.away_score, "corners": None if None in co else int(co[0] + co[1])})
    meetings = meetings[:H2H_MAX]
    wins_home = sum(1 for k in meetings if (k["score"].split("-")[0] > k["score"].split("-")[1]) == (k["homeId"] == str(home_id))
                    and k["score"].split("-")[0] != k["score"].split("-")[1])
    draws = sum(1 for k in meetings if k["score"].split("-")[0] == k["score"].split("-")[1])
    n = len(meetings)
    cs = [k["corners"] for k in meetings if k["corners"] is not None]
    return {"meetings": [{k: v for k, v in z.items() if k != "homeId"} for z in meetings], "n": n,
            "homeWins": wins_home, "draws": draws, "awayWins": n - wins_home - draws,
            "avgGoals": round(sum(k["goals"] for k in meetings) / n, 2) if n else None,
            "avgCorners": round(sum(cs) / len(cs), 1) if cs else None}


def simulate(db: Session, external_id: str) -> Optional[Dict[str, Any]]:
    m = db.query(Match).filter(Match.external_id == external_id).first()
    if m is None:
        return None
    sides = {mc.side: mc for mc in m.competitors}
    if "home" not in sides or "away" not in sides:
        return None
    home_id, away_id = sides["home"].competitor_id, sides["away"].competitor_id
    lh, la, _ = expected_goals_for_fixture(db, str(home_id), str(away_id), m.season or "", str(m.league_id) if m.league_id else None)
    out: Dict[str, Any] = {
        "home": sides["home"].competitor.name, "away": sides["away"].competitor.name,
        "league": m.league.name if m.league else None,
        "expectedGoals": {"home": round(lh, 2), "away": round(la, 2)},
        "goals": goal_markets(lh, la),
    }
    shape = _league_shape(db, m.league_id, m.match_date)
    hrows, arows = _team_matches(db, home_id, m.match_date, TEAM_MATCHES), _team_matches(db, away_id, m.match_date, TEAM_MATCHES)
    h_sc, h_co, hn = _profile(hrows)
    a_sc, a_co, an = _profile(arows)
    out["minutes"] = {
        "bands": minute_view(lh, la, shares(h_sc, shape), shares(h_co, shape), shares(a_sc, shape), shares(a_co, shape)),
        "leagueShape": [round(x, 3) for x in shape],
        "matchesUsed": {"home": hn, "away": an},
        "note": "Reparto de los goles esperados por tramo de minutos, con lo que cada equipo marca y recibe en sus últimos partidos, "
                "acercado a la forma de la liga.",
    }
    out["corners"] = corners_view(db, m, home_id, away_id)
    out["h2h"] = h2h_view(db, m, home_id, away_id)
    out["note"] = ("Descripción del partido más probable con datos anteriores; no se ha medido contra la cuota de la casa, "
                   "así que no es una señal de apuesta.")
    return out
