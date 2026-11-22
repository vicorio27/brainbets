"""How each player does against THIS rival, beyond the bare head-to-head count.

From every stored meeting of the two (deduplicated when two sources list the
same match) it reads, from each player's side: wins and losses (and since
2024), sets, straight-set defeats, tiebreaks and, where the feed has serve
statistics, the share of service games held against this rival compared with
his usual level. Short notes name what stands out ("pierde más tiebreaks con
él", "su saque baja contra él").

Information, not a price signal: not measured against the bookmaker. Small
samples are said as they are.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.domain.models import Match, MatchCompetitor, MatchScore

MIN_MEETINGS = 3        # below this there is nothing worth saying
BAD_RATE = 0.35         # wins / meetings at or under this, with MIN_NOTE meetings, is "no es bueno contra él"
MIN_NOTE = 5
MIN_TIEBREAKS = 3
MIN_SERVE_MATCHES = 3
HOLD_GAP = 0.08         # service games held vs his usual, in points


def _short(name: str) -> str:
    return str(name or "").split(" ")[0]


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def player_lines(me: str, rival: str, meetings: List[Dict[str, Any]],
                 usual_hold: Optional[float]) -> Dict[str, Any]:
    """meetings: from `me`'s side {date, won, sets_for, sets_against, tb_for, tb_against,
    serve: {"sgw", "sgt"} | None}."""
    n = len(meetings)
    if n < MIN_MEETINGS:
        return {"lines": [], "notes": [], "record": None}
    w = sum(1 for m in meetings if m["won"])
    recent = [m for m in meetings if m["date"].year >= 2024]
    sf = sum(m["sets_for"] for m in meetings)
    sa = sum(m["sets_against"] for m in meetings)
    straight = sum(1 for m in meetings if not m["won"] and m["sets_for"] == 0)
    tbf = sum(m["tb_for"] for m in meetings)
    tba = sum(m["tb_against"] for m in meetings)
    lines = [f"{me} {w}-{n - w} contra {rival}"
             + (f" (desde 2024: {sum(1 for m in recent if m['won'])}-{sum(1 for m in recent if not m['won'])})" if recent and len(recent) < n else "")
             + f"; sets {sf}-{sa}"
             + (f"; {straight} derrotas en 2 sets" if straight else "")]
    notes: List[str] = []
    if tbf + tba:
        lines.append(f"Tiebreaks contra {rival}: {me} {tbf}-{tba}")
        if tbf + tba >= MIN_TIEBREAKS and tba > tbf:
            notes.append(f"Pierde más tiebreaks de los que gana contra {rival} ({tbf}-{tba})")
    sv = [m["serve"] for m in meetings if m.get("serve") and m["serve"]["sgt"]]
    if len(sv) >= MIN_SERVE_MATCHES:
        held = sum(s["sgw"] for s in sv) / sum(s["sgt"] for s in sv)
        lines.append(f"Juegos de saque ganados contra {rival}: {_pct(held)} en {len(sv)} partidos"
                     + (f" (lo normal en él: {_pct(usual_hold)})" if usual_hold else ""))
        if usual_hold and usual_hold - held >= HOLD_GAP:
            notes.append(f"Su saque baja contra {rival}: {_pct(held)} de juegos de saque ganados contra {_pct(usual_hold)} normalmente")
        elif usual_hold and held - usual_hold >= HOLD_GAP:
            notes.append(f"Su saque sube contra {rival}: {_pct(held)} de juegos de saque ganados contra {_pct(usual_hold)} normalmente")
    if n >= MIN_NOTE and w / n <= BAD_RATE:
        notes.insert(0, f"No le ha ido bien contra {rival}: ganó {w} de {n}")
    elif n >= MIN_NOTE and w / n >= 1 - BAD_RATE:
        notes.insert(0, f"Le ha ido bien contra {rival}: ganó {w} de {n}")
    return {"lines": lines, "notes": notes, "record": f"{w}-{n - w}"}


def build(p1: str, p2: str, meetings_p1: List[Dict[str, Any]], hold1: Optional[float],
          hold2: Optional[float]) -> Optional[Dict[str, Any]]:
    """meetings_p1 are from p1's side; p2's are the same meetings flipped."""
    if len(meetings_p1) < MIN_MEETINGS:
        return None

    def flip(m):
        return {"date": m["date"], "won": not m["won"], "sets_for": m["sets_against"], "sets_against": m["sets_for"],
                "tb_for": m["tb_against"], "tb_against": m["tb_for"], "serve": m.get("serve_rival")}

    a = player_lines(p1, _short(p2), meetings_p1, hold1)
    b = player_lines(p2, _short(p1), [flip(m) for m in meetings_p1], hold2)
    return {"p1": a, "p2": b, "n": len(meetings_p1)}


# ---------- database ----------

def _serve_of(stats: Dict[str, Any], home: bool) -> Optional[Dict[str, int]]:
    s = ((stats.get("serve") or {}).get("home" if home else "away")) or {}
    try:
        sgt = int(s.get("serveGamesTotal") or 0)
        return {"sgw": int(s.get("serveGamesWon") or 0), "sgt": sgt} if sgt else None
    except (TypeError, ValueError):
        return None


def matchup_for_match(db: Session, match: Match, hold1: Optional[float] = None,
                      hold2: Optional[float] = None) -> Optional[Dict[str, Any]]:
    sides = {("p1" if c.side in ("player1", "home") else "p2"): c for c in match.competitors}
    if len(sides) != 2 or not match.match_date:
        return None
    c1, c2 = sides["p1"].competitor_id, sides["p2"].competitor_id
    mine = (db.query(MatchCompetitor, Match).join(Match, Match.id == MatchCompetitor.match_id)
            .filter(MatchCompetitor.competitor_id == c1, Match.status == "FINISHED",
                    Match.match_date < match.match_date).all())
    ids = [m.id for _, m in mine]
    if not ids:
        return None
    theirs = {mc.match_id: mc for mc in db.query(MatchCompetitor).filter(
        MatchCompetitor.match_id.in_(ids), MatchCompetitor.competitor_id == c2).all()}
    scores = {s.match_id: s for s in db.query(MatchScore).filter(
        MatchScore.match_id.in_(list(theirs)), MatchScore.period == "FULL_TIME").all()}
    rows: List[Dict[str, Any]] = []
    for mc, m in mine:
        if m.id not in theirs or m.id not in scores:
            continue
        sc = scores[m.id]
        home = mc.side in ("player1", "home")
        sf, sa = (sc.home_score, sc.away_score) if home else (sc.away_score, sc.home_score)
        if sf is None or sa is None or sf == sa:
            continue
        stats = (m.extra_data or {}).get("score_stats") or {}
        tbf = tba = 0
        for row in stats.get("sets") or []:
            try:
                x, y = int(row.get("p1") or 0), int(row.get("p2") or 0)
            except (TypeError, ValueError):
                continue
            if {x, y} == {7, 6}:
                if (x == 7) == home:
                    tbf += 1
                else:
                    tba += 1
        rows.append({"date": m.match_date, "won": sf > sa, "sets_for": sf, "sets_against": sa,
                     "tb_for": tbf, "tb_against": tba, "serve": _serve_of(stats, home),
                     "serve_rival": _serve_of(stats, not home), "has_stats": bool(stats)})
    # the same match can come from two sources: keep one per +-2 days, preferring the one with statistics
    rows.sort(key=lambda r: (r["date"], not r["has_stats"]))
    kept: List[Dict[str, Any]] = []
    for r in rows:
        dup = next((k for k in kept if abs((k["date"] - r["date"]).days) <= 2), None)
        if dup is None:
            kept.append(r)
        elif r["has_stats"] and not dup["has_stats"]:
            kept[kept.index(dup)] = r
    kept.sort(key=lambda r: r["date"], reverse=True)
    return build(sides["p1"].competitor.name, sides["p2"].competitor.name, kept, hold1, hold2)
