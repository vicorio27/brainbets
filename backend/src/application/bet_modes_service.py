"""Two ways of betting the same reading of the upcoming matches (pure, no DB).

Conservative (the user's own system: 17 of 18 won, 2026-10/11): per match the safest bet the
bookmaker prices - usually "X gana al menos un set" or a heavy favourite to win - as a single, plus
the safest 2-match combos, whatever their total price. When the data clearly backs the underdog
(head to head, form, load, news...: facts, not price), the conservative version of that reading is
"the underdog wins at least one set" (17-nov: Jodar 2-0 on hard vs Fils -> Jodar takes a set, 1.33).

Risky: that same reading bet straight (the underdog wins the match / the first set), and only when
there are clear arguments. A price alone (a book above the fair line) never makes a risky pick.

Neither has beaten the bookmaker's price when measured; the texts say so.
"""
from itertools import combinations
from typing import Any, Dict, List, Optional

VERY_SAFE = 0.85      # "muy segura"
SAFE = 0.75           # "segura"
BACKED_MIN = 0.65     # a set for a backed underdog counts from here
MAX_SINGLES = 12
MAX_COMBOS = 5
# Facts about the players. Left out: the point model and Elo (models that lost to the price),
# and tiebreak/decider (they say the match is close, not who wins it).
CLEAR_ARGS = {"h2h", "h2h_last", "form", "load", "layoff", "news_fav", "news_dog", "streak",
              "final_drought", "first_final"}
STRONG_ARGS = {"h2h"}   # winning the head to head is enough on its own
MAIN_KINDS = ("partido", "set1", "unSet", "sinCeder", "sets")


def clear_reasons(case: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in (case or {}).get("reasons") or [] if r.get("key") in CLEAR_ARGS]


def is_backed(case: Optional[Dict[str, Any]]) -> bool:
    """Clear arguments for the underdog: two facts, or winning the head to head."""
    rs = clear_reasons(case)
    return len(rs) >= 2 or any(r["key"] in STRONG_ARGS for r in rs)


def level(prob: float) -> str:
    return "muy segura" if prob >= VERY_SAFE else "segura" if prob >= SAFE else "con argumentos"


def _leg(m: Dict[str, Any], pick: Dict[str, Any], why: str, backed: bool = False) -> Dict[str, Any]:
    return {
        "matchId": m.get("matchId"),
        "match": f"{m.get('player1')} vs {m.get('player2')}",
        "eventDate": m.get("eventDate"),
        "eventTime": m.get("eventTime"),
        "tournament": m.get("tournament"),
        "kind": pick["kind"],
        "selector": pick.get("selector"),
        "label": pick["label"],
        "probability": pick["probability"],
        "odds": pick["odds"],
        "oddsKind": pick.get("oddsKind"),
        "bestOdds": pick.get("bestOdds") or pick["odds"],
        "bestBook": pick.get("bestBook"),
        "level": level(pick["probability"]),
        "backed": backed,
        "why": why,
    }


def _find(picks: List[Dict[str, Any]], kind: str, side: str) -> Optional[Dict[str, Any]]:
    return next((p for p in picks if p.get("kind") == kind and (p.get("selector") or {}).get("side") == side), None)


def conservative_for(m: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The safest priced bet of one match, or the backed underdog's set."""
    picks = [p for p in m.get("likelyPicks") or [] if p.get("source") == "casa" and p.get("kind") in MAIN_KINDS]
    case = m.get("underdogCase")
    if case and is_backed(case):
        dog_set = _find(picks, "unSet", case.get("side"))
        if dog_set and dog_set["probability"] >= BACKED_MIN:
            why = "Los datos respaldan a " + str(case.get("underdog")) + ": " + "; ".join(
                r["text"] for r in clear_reasons(case)) + " Versión segura: que gane al menos un set."
            return _leg(m, dog_set, why, backed=True)
    if not picks:
        return None
    best = max(picks, key=lambda p: p["probability"])
    if best["probability"] < SAFE:
        return None
    return _leg(m, best, "Lo más probable del partido según la casa.")


def risky_for(m: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The underdog straight, only with clear arguments behind him."""
    case = m.get("underdogCase")
    if not case or not is_backed(case):
        return None
    rs = clear_reasons(case)
    set1 = sum(r.get("market") == "set1" for r in rs) > len(rs) / 2
    opt = next((o for o in case.get("options") or [] if o.get("market") == ("set1" if set1 else "partido")), None)
    if not opt or not opt.get("odds"):
        return None
    safe = conservative_for(m)
    return {
        "matchId": m.get("matchId"),
        "match": f"{m.get('player1')} vs {m.get('player2')}",
        "eventDate": m.get("eventDate"),
        "eventTime": m.get("eventTime"),
        "tournament": m.get("tournament"),
        "kind": "set1" if set1 else "partido",
        "selector": {"side": case.get("side")},
        "label": f"{case.get('underdog')} {'gana el 1er set' if set1 else 'gana el partido'}",
        "probability": opt.get("marketProb"),
        "odds": opt["odds"],
        "oddsKind": "directa",
        "bestOdds": opt["odds"],
        "bestBook": None,
        "reasons": [{"text": r["text"], "evidence": r.get("evidence")} for r in rs],
        "safeVersion": safe if safe and safe.get("backed") else None,
        "note": case.get("note"),
    }


def build_modes(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    upcoming = [m for m in matches if m.get("status") == "SCHEDULED"]
    singles = [c for c in (conservative_for(m) for m in upcoming) if c]
    singles.sort(key=lambda c: -c["probability"])
    combos = []
    for a, b in combinations(singles, 2):
        prob = a["probability"] * b["probability"]
        combos.append({"legs": [a, b], "probability": round(prob, 4),
                       "odds": round(a["odds"] * b["odds"], 3),
                       "bestOdds": round(a["bestOdds"] * b["bestOdds"], 3)})
    combos.sort(key=lambda c: -c["probability"])
    risky = [r for r in (risky_for(m) for m in upcoming) if r]
    risky.sort(key=lambda r: -(len(r["reasons"])))
    return {
        "conservative": {"singles": singles[:MAX_SINGLES], "combos": combos[:MAX_COMBOS]},
        "risky": risky,
        "thresholds": {"verySafe": VERY_SAFE, "safe": SAFE, "backedSet": BACKED_MIN},
    }
