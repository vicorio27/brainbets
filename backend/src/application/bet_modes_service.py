"""Two ways of betting the same reading of the upcoming matches (pure, no DB).

Conservative (the user's own system: 17 of 18 won, 2026-10/11): per match the safest bet the
bookmaker prices - usually "X gana al menos un set" or a heavy favourite to win - as a single, plus
the safest 2-match combos, whatever their total price. When the data clearly backs a player (usually the underdog)
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
EST_MARGIN = 1.07     # bookmaker margin assumed for an estimated price
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


def _cases(m: Dict[str, Any]) -> Dict[str, Optional[Dict[str, Any]]]:
    """Arguments for each player (underdog_service.player_case), computed once per match."""
    if "_cases" not in m:
        from src.application.underdog_service import player_case
        cases = {side: player_case(m, side) for side in ("p1", "p2")}
        dog = m.get("underdogCase") or {}
        if dog.get("side") in cases and cases[dog["side"]] is None:
            cases[dog["side"]] = dog   # already computed upstream
        m["_cases"] = cases
    return m["_cases"]


def _priced(m: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [p for p in m.get("likelyPicks") or [] if p.get("source") == "casa" and p.get("kind") in MAIN_KINDS]


def _set_pick(m: Dict[str, Any], side: str) -> Optional[Dict[str, Any]]:
    """'X gana al menos un set' even under 50% (likelyPicks keeps only the likely ones):
    the bookmaker's own market, else the set-betting board estimate from the player's case."""
    found = _find(_priced(m), "unSet", side)
    if found:
        return found
    name = m.get("player1" if side == "p1" else "player2")
    q = ((m.get("oddsMarkets") or {}).get("oneSet") or {}).get(side) or {}
    try:
        yes, no = float(q["yes"]), float(q["no"])
        if yes > 1 and no > 1:
            return {"kind": "unSet", "selector": {"side": side}, "label": f"{name} gana al menos un set",
                    "probability": round((1 / yes) / (1 / yes + 1 / no), 4), "odds": yes, "oddsKind": "directa"}
    except (KeyError, TypeError, ValueError):
        pass
    opt = next((o for o in (_cases(m).get(side) or {}).get("options") or [] if o.get("market") == "unSet"), None)
    if opt and opt.get("marketProb"):
        p = opt["marketProb"]
        return {"kind": "unSet", "selector": {"side": side}, "label": f"{name} gana al menos un set",
                "probability": p, "odds": round(max(1.01, 1 / (p * EST_MARGIN)), 2), "oddsKind": "aprox"}
    return None


def _backed_set(m: Dict[str, Any], side: str) -> Optional[Dict[str, Any]]:
    """'X gana al menos un set' for a player the data backs, with the arguments as the reason."""
    case = _cases(m).get(side)
    if not case or not is_backed(case):
        return None
    pick = _set_pick(m, side)
    if not pick or pick["probability"] < BACKED_MIN:
        return None
    why = "Los datos respaldan a " + str(case.get("underdog")) + ": " + " ".join(
        r["text"] for r in clear_reasons(case)) + " Versión segura: que gane al menos un set."
    return _leg(m, pick, why, backed=True)


def conservative_for(m: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The safest priced bet of one match, or the backed underdog's set. (A backed favourite's
    safest bet is already the most likely one.)"""
    dog = (m.get("underdogCase") or {}).get("side")
    backed = _backed_set(m, dog) if dog else None
    if backed:
        return backed
    picks = _priced(m)
    if not picks:
        return None
    best = max(picks, key=lambda p: p["probability"])
    if best["probability"] < SAFE:
        return None
    return _leg(m, best, "Lo más probable del partido según la casa.")


def risky_for_side(m: Dict[str, Any], side: str) -> Optional[Dict[str, Any]]:
    """That player straight (match, or 1st set when most arguments are about the start),
    only with clear arguments behind him."""
    case = _cases(m).get(side)
    if not case or not is_backed(case):
        return None
    rs = clear_reasons(case)
    set1 = sum(r.get("market") == "set1" for r in rs) > len(rs) / 2
    opt = next((o for o in case.get("options") or [] if o.get("market") == ("set1" if set1 else "partido")), None)
    if not opt or not opt.get("odds"):
        return None
    return {
        "matchId": m.get("matchId"),
        "match": f"{m.get('player1')} vs {m.get('player2')}",
        "eventDate": m.get("eventDate"),
        "eventTime": m.get("eventTime"),
        "tournament": m.get("tournament"),
        "kind": "set1" if set1 else "partido",
        "selector": {"side": side},
        "label": f"{case.get('underdog')} {'gana el 1er set' if set1 else 'gana el partido'}",
        "probability": opt.get("marketProb"),
        "odds": opt["odds"],
        "oddsKind": "directa",
        "bestOdds": opt["odds"],
        "bestBook": None,
        "favourite": (opt.get("marketProb") or 0) >= 0.5,
        "reasons": [{"text": r["text"], "evidence": r.get("evidence")} for r in rs],
        "safeVersion": _backed_set(m, side),
        "note": case.get("note"),
    }


def risky_for(m: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The underdog's risky pick (kept for callers that want one per match)."""
    dog = (m.get("underdogCase") or {}).get("side")
    return risky_for_side(m, dog) if dog else None


def perspectives(m: Dict[str, Any]) -> Dict[str, Any]:
    """Both players' view of one match: the safe bet and the risky one for each."""
    picks = _priced(m)
    sides = []
    for side in ("p1", "p2"):
        case = _cases(m).get(side) or {}
        win = _find(picks, "partido", side)
        safe_set = _set_pick(m, side)
        safe = _backed_set(m, side)
        if not safe and safe_set:
            safe = _leg(m, safe_set, "Que gane al menos un set: con un set le basta.")
        sides.append({
            "side": side,
            "player": m.get("player1" if side == "p1" else "player2"),
            "winProbability": case.get("marketProb"),
            "odds": case.get("odds"),
            "favourite": (case.get("marketProb") or 0) > 0.5,
            "reasons": [{"text": r["text"], "evidence": r.get("evidence")} for r in clear_reasons(case)],
            "conservative": safe,
            "risky": risky_for_side(m, side),
            "win": _leg(m, win, "Que gane el partido.") if win else None,
        })
    return {
        "matchId": m.get("matchId"),
        "match": f"{m.get('player1')} vs {m.get('player2')}",
        "eventDate": m.get("eventDate"),
        "eventTime": m.get("eventTime"),
        "tournament": m.get("tournament"),
        "sides": sides,
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
    risky = [r for m in upcoming for r in (risky_for_side(m, s) for s in ("p1", "p2")) if r]
    risky.sort(key=lambda r: -(len(r["reasons"])))
    return {
        "conservative": {"singles": singles[:MAX_SINGLES], "combos": combos[:MAX_COMBOS]},
        "risky": risky,
        "matches": [perspectives(m) for m in upcoming if _cases(m).get("p1") or _priced(m)],
        "thresholds": {"verySafe": VERY_SAFE, "safe": SAFE, "backedSet": BACKED_MIN},
    }
