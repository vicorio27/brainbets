"""How a player is playing lately compared with HIS OWN usual level.

For each player of an upcoming match: his last RECENT finished matches against the BASE_MAX before
them, on serve (service games held, first serves in, first-serve points won, aces), return (return
games won), first sets and results. A metric is flagged only when the gap passes its threshold.
It compares the player with himself, not with the tour, and does not adjust for how good the
recent opponents were. Not measured against the price: information, not a value signal.
"""
from datetime import timedelta
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from src.domain.models import Match, MatchCompetitor, MatchScore

RECENT = 5
BASE_MAX = 30
BASE_MIN = 8
LOOKBACK_DAYS = 400
TOP_RANK = 20   # "es el #N del mundo, pero..." from here up

# key, label, kind, threshold (points of a rate, or relative change for a mean)
METRICS = [
    ("hold", "Juegos de saque ganados", "rate", 0.05),
    ("firstIn", "Primer saque adentro", "rate", 0.04),
    ("firstWon", "Puntos ganados con el primer saque", "rate", 0.04),
    ("aces", "Aces por partido", "mean", 0.30),
    ("break", "Juegos de resto ganados", "rate", 0.05),
    ("set1", "Primeros sets ganados", "rate", 0.25),
    ("wins", "Partidos ganados", "rate", 0.25),
]


def _int(x: Any) -> Optional[int]:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def match_row(stats: Dict[str, Any], is_home: bool, won: bool) -> Dict[str, Any]:
    """One finished match from one player's side: raw counts, so windows pool them."""
    row: Dict[str, Any] = {"won": won}
    sets = stats.get("sets") or []
    if sets:
        a, b = _int(sets[0].get("p1")), _int(sets[0].get("p2"))
        if a is not None and b is not None and a != b:
            row["set1"] = (a > b) == is_home
    mine = (stats.get("serve") or {}).get("home" if is_home else "away") or {}
    for key, name in (("sgw", "serveGamesWon"), ("sgt", "serveGamesTotal"), ("rgw", "returnGamesWon"),
                      ("rgt", "returnGamesTotal"), ("fw", "firstServeWon"), ("ft", "firstServeTotal"),
                      ("st", "secondServeTotal"), ("spt", "servePtsTotal")):
        v = _int(mine.get(name))
        if v is not None:
            row[key] = v
    aces = _int(stats.get("homeAces" if is_home else "awayAces"))
    if aces is not None:
        row["aces"] = aces
    return row


def _value(rows: List[Dict[str, Any]], key: str):
    """(value, sample) of one metric over a window of rows."""
    def pooled(num, den, invert=False):
        use = [r for r in rows if r.get(den)]
        tot = sum(r[den] for r in use)
        if not tot:
            return None, 0
        part = sum(r.get(num) or 0 for r in use) / tot
        return (1 - part if invert else part), len(use)

    if key == "hold":
        return pooled("sgw", "sgt")
    if key == "break":
        return pooled("rgw", "rgt")
    if key == "firstWon":
        return pooled("fw", "ft")
    if key == "firstIn":
        return pooled("st", "spt", invert=True)   # first serves in = serve points not played on a second serve
    if key == "aces":
        use = [r["aces"] for r in rows if "aces" in r]
        return (sum(use) / len(use), len(use)) if use else (None, 0)
    if key == "set1":
        use = [r["set1"] for r in rows if "set1" in r]
        return (sum(use) / len(use), len(use)) if use else (None, 0)
    use = [r["won"] for r in rows]
    return (sum(use) / len(use), len(use)) if use else (None, 0)


def _fmt(kind: str, v: float) -> str:
    return f"{v:.1f}" if kind == "mean" else f"{round(v * 100)}%"


def form_report(rows: List[Dict[str, Any]], ranking: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """rows: the player's finished matches, most recent first (match_row)."""
    recent, base = rows[:RECENT], rows[RECENT:RECENT + BASE_MAX]
    if len(recent) < RECENT or len(base) < BASE_MIN:
        return None
    metrics = []
    for key, label, kind, thr in METRICS:
        r, nr = _value(recent, key)
        b, nb = _value(base, key)
        if r is None or b is None or nr < 3 or nb < BASE_MIN:
            continue
        delta = r - b
        if kind == "mean":
            hit = b > 0 and abs(delta) / b >= thr and abs(delta) >= 1.5
        else:
            hit = abs(delta) >= thr
        metrics.append({
            "key": key, "label": label, "recent": round(r, 4), "base": round(b, 4), "delta": round(delta, 4),
            "recentSample": nr, "baseSample": nb,
            "trend": ("mejor" if delta > 0 else "peor") if hit else None,
            "text": f"{label}: {_fmt(kind, r)} en sus últimos {nr} (lo normal en él: {_fmt(kind, b)})",
        })
    if not metrics:
        return None
    better = [m for m in metrics if m["trend"] == "mejor"]
    worse = [m for m in metrics if m["trend"] == "peor"]
    if len(better) >= 2 and not worse:
        level, head = "bien", "Viene jugando por encima de su nivel"
    elif len(worse) >= 2 and not better:
        level, head = "mal", "Viene jugando por debajo de su nivel"
    elif better and worse:
        level, head = "mixto", "Va mejor en unas cosas y peor en otras"
    elif better or worse:
        level, head = "leve", "Casi en su nivel, con una diferencia"
    else:
        level, head = "normal", "En su nivel habitual"
    if ranking and ranking <= TOP_RANK and level == "mal":
        head = f"Es el #{ranking} del mundo, pero viene jugando por debajo de su nivel"
    elif ranking and ranking > 50 and level == "bien":
        head = f"Es el #{ranking} del mundo, pero viene jugando por encima de su nivel"
    flagged = [m["text"] for m in (better[:2] + worse[:2] if level == "mixto" else better + worse)]
    return {
        "level": level,
        "headline": head + (": " + "; ".join(flagged[:3]) + "." if flagged else "."),
        "metrics": metrics,
        "recentMatches": len(recent),
        "baseMatches": len(base),
        "note": "Comparado con él mismo (sus últimos 5 contra los 30 anteriores). No ajusta por la calidad de los rivales "
                "y no se ha medido contra la cuota.",
    }


def form_for_matches(db: Session, matches: Iterable[Match]) -> Dict[Any, Dict[str, Any]]:
    """{match_id: {"p1": report|None, "p2": report|None}} for matches not finished yet."""
    targets = [m for m in matches if m.match_date and m.status != "FINISHED"]
    if not targets:
        return {}
    sides: Dict[Any, Dict[str, MatchCompetitor]] = {}
    comp_ids = set()
    for m in targets:
        for mc in m.competitors:
            sides.setdefault(m.id, {})["p1" if mc.side in ("player1", "home") else "p2"] = mc
            comp_ids.add(mc.competitor_id)
    end = max(m.match_date for m in targets)
    start = min(m.match_date for m in targets) - timedelta(days=LOOKBACK_DAYS)
    links = (
        db.query(MatchCompetitor, Match)
        .join(Match, Match.id == MatchCompetitor.match_id)
        .filter(MatchCompetitor.competitor_id.in_(comp_ids), Match.status == "FINISHED",
                Match.match_date >= start, Match.match_date < end)
        .order_by(Match.match_date.desc())
        .all()
    )
    ids = list({m.id for _, m in links})
    scores = {s.match_id: s for s in db.query(MatchScore).filter(
        MatchScore.match_id.in_(ids), MatchScore.period == "FULL_TIME").all()} if ids else {}
    history: Dict[Any, List[Any]] = {}
    for mc, m in links:
        sc = scores.get(m.id)
        if not sc or sc.home_score is None or sc.away_score is None or sc.home_score == sc.away_score:
            continue
        is_home = mc.side in ("player1", "home")
        won = (sc.home_score > sc.away_score) == is_home
        history.setdefault(mc.competitor_id, []).append((m.match_date, match_row((m.extra_data or {}).get("score_stats") or {}, is_home, won)))
    out = {}
    for m in targets:
        res = {}
        for side, mc in sides.get(m.id, {}).items():
            rows = [r for d, r in history.get(mc.competitor_id, []) if d < m.match_date]
            res[side] = form_report(rows, mc.pre_match_ranking)
        out[m.id] = res
    return out
