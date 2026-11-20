"""What the price alone does not tell: what each player has at stake and in what conditions.

The user's own criteria (2026-11-19, Shelton and Zverev at the Finals):
- stakes: what a win or a loss changes (Finals group: qualified / out / depends), plus "en juego" news;
- new coach: news tagged "entrenador" or headlines that talk about a coach;
- indoor: record under a roof vs outdoor hard, last INDOOR_YEARS years (shown when this match is indoor);
- top 10: wins against top-10 rivals this calendar year, and the date of the last one.

Measured 2026-11-19 against Pinnacle closing odds, ATP 2011-2020 (scratchpad research_context.py,
hypotheses written first): indoor gap and top-10 record are already in the price; in the Finals
round robin a player with nothing at stake won 38.9% vs 47.7% (n=18, too few to act on).
"""
import itertools
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from src.domain.models import League, Match, MatchCompetitor, MatchScore

INDOOR_YEARS = 3
INDOOR_MIN = 10          # indoor matches needed to say anything
INDOOR_GAP = 0.08        # "mejor / peor bajo techo" from 8 points of win rate
TOP10_MIN = 3            # top-10 matches needed to call the record good or bad
RANK_NEAR_DAYS = 90      # a rival without a ranking on that match takes his nearest known one
GROUP_STAGE_MATCHES = 12  # Finals round robin: 2 groups x 6 matches

# Always under a roof (word match on the tournament name, accents removed)
INDOOR_ALWAYS = (
    "turin", "finals", "masters cup", "basel", "swiss indoors", "vienna", "vienna open", "rotterdam",
    "marseille", "open 13", "montpellier", "occitanie", "sofia", "stockholm", "nordic open", "antwerp",
    "european open", "metz", "moselle", "dallas", "st petersburg", "st. petersburg", "moscow", "kremlin",
    "astana", "almaty", "laver cup", "next gen", "jeddah", "bnp paribas masters", "hellenic", "athens",
    "cologne", "koln", "gijon", "florence", "firenze", "brussels", "memphis", "new york open", "milan",
)
# Under a roof only in the autumn/winter edition
INDOOR_AUTUMN = ("paris", "lyon", "belgrade")
UNKNOWN = ("davis cup",)   # each tie picks its venue

COACH_WORDS = re.compile(r"\b(coach|coaching|entrenador|entrenadora|tecnico|técnico|ferrero)\b", re.I)


def _plain(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9. ]+", " ", s)


def _has(name: str, words: Sequence[str]) -> bool:
    return any(re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", name) for w in words)


def is_indoor(tournament: Optional[str], when: Optional[datetime], court: Optional[str] = None) -> Optional[bool]:
    """True / False from the stored court (historical data) or the tournament name; None if unknown."""
    if court:
        c = court.strip().lower()
        if c in ("indoor", "outdoor"):
            return c == "indoor"
    name = _plain(tournament or "")
    if not name:
        return None
    if _has(name, UNKNOWN):
        return None
    if _has(name, INDOOR_ALWAYS):
        return True
    if when is not None and when.month >= 9 and _has(name, INDOOR_AUTUMN):
        return True
    return False


# ---------- pure pieces ----------

def indoor_item(rows: List[Tuple[bool, bool]]) -> Optional[Dict[str, Any]]:
    """rows = [(indoor, won)] of hard-court matches. None when there are too few indoor ones."""
    ind = [w for i, w in rows if i]
    out = [w for i, w in rows if not i]
    if len(ind) < INDOOR_MIN:
        return None
    ri = sum(ind) / len(ind)
    text = f"{round(ri * 100)}% ({sum(ind)}-{len(ind) - sum(ind)})"
    short = f"{round(ri * 100)}%"
    tone = "neutral"
    if out:
        ro = sum(out) / len(out)
        text += f" vs {round(ro * 100)}% al aire libre en cemento ({sum(out)}-{len(out) - sum(out)})"
        short += f" vs {round(ro * 100)}%"
        if ri - ro >= INDOOR_GAP:
            tone = "good"
        elif ro - ri >= INDOOR_GAP:
            tone = "bad"
    return {"key": "indoor", "label": "Bajo techo", "tone": tone, "short": short,
            "text": text + f", últimos {INDOOR_YEARS} años",
            "detail": "Bajo techo según la cancha guardada (histórico) o el nombre del torneo."}


def top10_item(rows: List[Dict[str, Any]], year: int, opp_rank: Optional[int]) -> Optional[Dict[str, Any]]:
    """rows = [{date, won, rank, rival}] of this year's matches against a rival ranked 1-10."""
    if not rows and not (opp_rank and opp_rank <= 10):
        return None
    w = [r for r in rows if r["won"]]
    n = len(rows)
    text = f"{len(w)}-{n - len(w)} en {year}"
    if n and not w:
        text += " (ninguna victoria)"
    tone = "neutral"
    if n >= TOP10_MIN and not w:
        tone = "bad"
    elif n >= TOP10_MIN and len(w) / n >= 0.5:
        tone = "good"
    detail = []
    if w:
        last = max(w, key=lambda r: r["date"])
        detail.append(f"Última victoria: {last['rival']} (#{last['rank']}) el {last['date'].strftime('%Y-%m-%d')}.")
    if opp_rank and opp_rank <= 10:
        detail.append(f"Hoy juega contra un top 10 (#{opp_rank}).")
        if n and not w:
            text += "; hoy tiene otra oportunidad"
    detail.append("Ranking del rival en ese partido (o el más cercano conocido).")
    return {"key": "top10", "label": "Contra top 10", "tone": tone, "short": f"{len(w)}-{n - len(w)}",
            "text": text, "detail": " ".join(detail)}


def _status(wins: Dict[str, int], player: str) -> str:
    mine = wins[player]
    more = sum(1 for p, v in wins.items() if p != player and v > mine)
    equal = sum(1 for p, v in wins.items() if p != player and v == mine)
    if more >= 2:
        return "out"
    if more + equal < 2:
        return "in"
    return "tie"


def group_stakes(results: List[Tuple[Any, Any]], remaining: List[Tuple[Any, Any]],
                 player: Any, opponent: Any) -> Dict[str, frozenset]:
    """Round robin by wins only, top 2 go through. For 'win' and 'lose': the set of outcomes over
    every result of the other unplayed matches: 'in', 'out', 'tie' (level on wins with others at
    the cut, decided by sets and games, which this does not model).

    results = finished (winner, loser); remaining = unplayed pairs other than this one.
    """
    players = {p for pair in results + remaining + [(player, opponent)] for p in pair}
    base = {p: 0 for p in players}
    for w, _ in results:
        base[w] += 1
    out = {}
    for label, winner in (("win", player), ("lose", opponent)):
        seen = set()
        for combo in itertools.product((0, 1), repeat=len(remaining)):
            wins = dict(base)
            wins[winner] += 1
            for (a, b), pick in zip(remaining, combo):
                wins[a if pick == 0 else b] += 1
            seen.add(_status(wins, player))
        out[label] = frozenset(seen)
    return out


SAY = {
    frozenset({"in"}): "pasa a semis",
    frozenset({"out"}): "queda afuera",
    frozenset({"tie"}): "queda empatado a victorias (se define por sets y games)",
    frozenset({"in", "tie"}): "pasa, o queda en un empate a victorias",
    frozenset({"in", "out"}): "pasa o no según el otro partido",
    frozenset({"tie", "out"}): "queda afuera salvo un empate a victorias",
    frozenset({"in", "tie", "out"}): "depende del otro partido",
}


def stakes_item(record: Tuple[int, int], st: Dict[str, frozenset]) -> Dict[str, Any]:
    w, l = record
    head = f"Va {w}-{l} en el grupo"
    win, lose = st["win"], st["lose"]
    rec = f"{w}-{l}"
    if win == {"out"}:
        return {"key": "stakes", "label": "Qué se juega", "tone": "bad", "short": f"{rec} · eliminado",
                "text": f"{head}: ya está eliminado, juega sin nada en juego",
                "detail": "Aunque gane no pasa a semifinales."}
    if lose == {"in"}:
        return {"key": "stakes", "label": "Qué se juega", "tone": "neutral", "short": f"{rec} · ya en semis",
                "text": f"{head}: ya está en semifinales pase lo que pase",
                "detail": "Puede dosificarse: perder no le cambia nada."}
    # the match matters when winning can put him through and losing cannot
    tone = "good" if "in" in win and "in" not in lose else "neutral"
    text = f"{head}: si gana {SAY[win]}; si pierde {SAY[lose]}"
    short = f"{rec} · todo o nada" if (win == {"in"} and lose == {"out"}) else f"{rec} · " + (
        "le sirve ganar" if tone == "good" else "depende")
    return {"key": "stakes", "label": "Qué se juega", "tone": tone, "short": short, "text": text,
            "detail": "Por victorias, con los partidos del grupo que faltan; un empate a victorias se define por sets y games."}


def news_items(news: Optional[Dict[str, Any]], side: str) -> List[Dict[str, Any]]:
    """'en juego' and coach items from the stored news of this match (side = 'player1' / 'player2')."""
    if not news:
        return []
    out, seen = [], set()
    for it in news.get(side) or []:
        f = it.get("factor")
        if f == "en_juego" and "stakes_news" not in seen:
            seen.add("stakes_news")
            txt = it.get("note") or it.get("headline")
            out.append({"key": "stakes_news", "label": "En juego", "tone": "good", "short": txt[:70],
                        "text": txt, "detail": it.get("headline")})
        elif f == "entrenador" and "coach" not in seen:
            seen.add("coach")
            txt = it.get("note") or it.get("headline")
            out.append({"key": "coach", "label": "Entrenador", "tone": "neutral", "short": txt[:70],
                        "text": txt, "detail": it.get("headline")})
    if "coach" not in seen:
        for it in ((news.get("latest") or {}).get(side)) or []:
            if COACH_WORDS.search(it.get("headline") or ""):
                out.append({"key": "coach", "label": "Entrenador", "tone": "neutral", "short": it["headline"][:70],
                            "text": f"(titular) {it['headline']}", "detail": it.get("source")})
                break
    return out


# ---------- database ----------

def _side(mc: MatchCompetitor) -> str:
    return "p1" if mc.side in ("player1", "home") else "p2"


def _winner_side(m: Match, sc: Optional[MatchScore]) -> Optional[str]:
    from src.application.h2h_service import meeting_winner
    w = meeting_winner(m.external_id, sc.home_score if sc else None, sc.away_score if sc else None)
    return {"player1": "p1", "player2": "p2"}.get(w) if w else None


def _finals_like(name: Optional[str]) -> bool:
    n = _plain(name or "")
    return ("finals" in n or "masters cup" in n) and "davis" not in n


def _group_context(db: Session, m: Match) -> Dict[str, Dict[str, Any]]:
    """{competitor_id: stakes item} for a Finals round-robin match."""
    start = m.match_date - timedelta(days=12)
    ed = (db.query(Match).filter(Match.league_id == m.league_id, Match.match_date >= start,
                                 Match.match_date <= m.match_date + timedelta(days=8))
          .order_by(Match.match_date.asc()).all())
    group_stage = ed[:GROUP_STAGE_MATCHES]
    if m.id not in {x.id for x in group_stage}:
        return {}
    sides = {x.id: {_side(mc): mc.competitor_id for mc in x.competitors} for x in group_stage}
    # groups = connected players (each group is a round robin of 4)
    adj: Dict[Any, set] = {}
    for s in sides.values():
        if "p1" in s and "p2" in s:
            adj.setdefault(s["p1"], set()).add(s["p2"])
            adj.setdefault(s["p2"], set()).add(s["p1"])
    me = sides.get(m.id) or {}
    if "p1" not in me or "p2" not in me:
        return {}
    group, todo = set(), [me["p1"]]
    while todo:
        p = todo.pop()
        if p not in group:
            group.add(p)
            todo.extend(adj.get(p, ()))
    if len(group) != 4:
        return {}
    ids = [x.id for x in group_stage]
    scores = {s.match_id: s for s in db.query(MatchScore).filter(
        MatchScore.match_id.in_(ids), MatchScore.period == "FULL_TIME").all()}
    results, remaining = [], []
    for x in group_stage:
        s = sides[x.id]
        if x.id == m.id or s.get("p1") not in group:
            continue
        w = _winner_side(x, scores.get(x.id)) if x.status == "FINISHED" else None
        if w:
            results.append((s[w], s["p2" if w == "p1" else "p1"]))
        elif x.status != "CANCELLED":
            remaining.append((s["p1"], s["p2"]))
    out = {}
    for side, opp in (("p1", "p2"), ("p2", "p1")):
        pid = me[side]
        rec = (sum(1 for w, _ in results if w == pid), sum(1 for _, l in results if l == pid))
        out[pid] = stakes_item(rec, group_stakes(results, remaining, pid, me[opp]))
    return out


def _history(db: Session, comp_ids: Iterable[Any], start: datetime, end: datetime):
    links = (db.query(MatchCompetitor, Match)
             .join(Match, Match.id == MatchCompetitor.match_id)
             .filter(MatchCompetitor.competitor_id.in_(list(comp_ids)), Match.status == "FINISHED",
                     Match.match_date >= start, Match.match_date < end)
             .all())
    ids = list({m.id for _, m in links})
    scores = {s.match_id: s for s in db.query(MatchScore).filter(
        MatchScore.match_id.in_(ids), MatchScore.period == "FULL_TIME").all()} if ids else {}
    opp: Dict[Any, List[MatchCompetitor]] = {}
    if ids:
        for mc in db.query(MatchCompetitor).filter(MatchCompetitor.match_id.in_(ids)).all():
            opp.setdefault(mc.match_id, []).append(mc)
    leagues = {lg.id: lg.name for lg in db.query(League).filter(
        League.id.in_(list({m.league_id for _, m in links if m.league_id}))).all()} if links else {}
    return links, scores, opp, leagues


def context_for_matches(db: Session, matches: Iterable[Match]) -> Dict[str, Dict[str, Any]]:
    """{external_id: {"p1": {"items": [...]}, "p2": {...}}} for tennis matches still to play."""
    from src.application.tennis_stats_service import normalize_surface

    targets = [m for m in matches if m.match_date and m.status not in ("FINISHED", "CANCELLED")]
    if not targets:
        return {}
    comp_ids = {mc.competitor_id for m in targets for mc in m.competitors}
    end = max(m.match_date for m in targets)
    start = min(m.match_date for m in targets) - timedelta(days=365 * INDOOR_YEARS + 1)
    links, scores, opp, leagues = _history(db, comp_ids, start, end)

    # rival rankings near each date, for matches with no ranking stored on them
    rank_rows = (db.query(MatchCompetitor.competitor_id, Match.match_date, MatchCompetitor.pre_match_ranking)
                 .join(Match, Match.id == MatchCompetitor.match_id)
                 .filter(MatchCompetitor.pre_match_ranking.isnot(None),
                         Match.match_date >= datetime(min(m.match_date for m in targets).year, 1, 1,
                                                      tzinfo=end.tzinfo) - timedelta(days=RANK_NEAR_DAYS),
                         Match.match_date <= end)
                 .all())
    known: Dict[Any, List[Tuple[datetime, int]]] = {}
    for cid, d, r in rank_rows:
        known.setdefault(cid, []).append((d, r))

    def rank_at(cid, d, own):
        if own:
            return own
        best = None
        for kd, r in known.get(cid, ()):
            gap = abs((kd - d).days)
            if gap <= RANK_NEAR_DAYS and (best is None or gap < best[0]):
                best = (gap, r)
        return best[1] if best else None

    per_player: Dict[Any, List[Dict[str, Any]]] = {}
    for mc, m in links:
        w = _winner_side(m, scores.get(m.id))
        if not w:
            continue
        rival = next((o for o in opp.get(m.id, ()) if o.competitor_id != mc.competitor_id), None)
        ex = m.extra_data or {}
        per_player.setdefault(mc.competitor_id, []).append({
            "date": m.match_date, "won": w == _side(mc),
            "surface": normalize_surface(ex.get("surface") or ex.get("ground_type")),
            "indoor": is_indoor(leagues.get(m.league_id), m.match_date, ex.get("court")),
            "rival": rival.competitor.name if rival else None,
            "rank": rank_at(rival.competitor_id, m.match_date, rival.pre_match_ranking) if rival else None,
        })

    out = {}
    for m in targets:
        league = m.league.name if m.league else None
        indoor_now = is_indoor(league, m.match_date, (m.extra_data or {}).get("court"))
        try:
            stakes = _group_context(db, m) if _finals_like(league) else {}
        except Exception:
            stakes = {}
        news = (m.extra_data or {}).get("player_news")
        sides = {_side(mc): mc for mc in m.competitors}
        res = {}
        for side, mc in sides.items():
            other = sides.get("p2" if side == "p1" else "p1")
            rows = [r for r in per_player.get(mc.competitor_id, []) if r["date"] < m.match_date]
            items: List[Dict[str, Any]] = []
            if mc.competitor_id in stakes:
                items.append(stakes[mc.competitor_id])
            items.extend(news_items(news, "player1" if side == "p1" else "player2"))
            if indoor_now:
                cut = m.match_date - timedelta(days=365 * INDOOR_YEARS)
                hard = [(r["indoor"], r["won"]) for r in rows
                        if r["date"] >= cut and r["indoor"] is not None and (r["indoor"] or r["surface"] == "hard")]
                it = indoor_item(hard)
                if it:
                    items.append(it)
            year = m.match_date.year
            top = [r for r in rows if r["date"].year == year and r["rank"] and r["rank"] <= 10]
            opp_rank = rank_at(other.competitor_id, m.match_date, other.pre_match_ranking) if other else None
            it = top10_item(top, year, opp_rank)
            if it:
                items.append(it)
            res[side] = {"player": mc.competitor.name, "items": items}
        out[m.external_id] = res
    return out
