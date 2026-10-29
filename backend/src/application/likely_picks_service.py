"""The most likely bets of a tennis match, however little they pay.

The user bets favourites at low prices ("Alcaraz wins the first set", "Zverev
takes at least a set off Griekspoor") and wants each match to list what is most
likely to come in. Probabilities are the bookmaker's without its margin; they
come from:
  * matchWinner / set1Winner: direct prices,
  * setBetting (the exact set score board): at least one set (= handicap +1.5
    sets at the bookmaker), without dropping a set, and 2 vs 3 sets.

Only outcomes at 50% or more are listed, most likely first. "Most likely" is not
"profitable": see the history each pick carries (best_bets_service.band_history).
"""
from typing import Any, Dict, List, Optional, Tuple

MIN_PROB = 0.50
STALE_GAP = 0.06       # same as best_bets_service: a best price this far above the reference may be stale
DEFAULT_MARGIN = 1.06   # a two-way tennis market's usual overround, when the match price is missing
MAX_PICKS = 4
# History key of each pick kind (best_bets_service.band_history).
# Kinds whose history was measured at the bookmaker's own price, so its yield means something.
PRICED_HISTORY = {"partido", "set1", "sinCeder"}
HISTORY_KEY = {"partido": "Match Winner", "set1": "Set 1 Winner", "unSet": "One Set",
               "sinCeder": "Straight Sets", "sets": "Total Sets"}


def _pair(odds: Any) -> Optional[Tuple[float, float]]:
    try:
        a, b = float(odds["p1"]), float(odds["p2"])
    except (KeyError, TypeError, ValueError):
        return None
    return (a, b) if a > 1 and b > 1 else None


def board_outcomes(board: Any) -> Optional[Dict[str, Dict[str, Tuple[float, Optional[float]]]]]:
    """Set-score board ("2:0" keys from player1's side) -> {p1|p2|match: {kind: (fair, price)}}.

    `price` is the bookmaker's own when the outcome is a single board line and
    None when it adds several lines (at least one set, the number of sets):
    adding prices adds the margin once per line, so that sum is no price.
    """
    if not isinstance(board, dict):
        return None
    try:
        inv = {k: 1 / float(v) for k, v in board.items() if float(v) > 1}
    except (TypeError, ValueError):
        return None
    bo5 = "3:0" in inv or "0:3" in inv
    keys = ("3:0", "3:1", "3:2", "2:3", "1:3", "0:3") if bo5 else ("2:0", "2:1", "1:2", "0:2")
    if any(k not in inv for k in keys):
        return None
    total = sum(inv[k] for k in keys)
    win = keys[0].split(":")[0]

    def outcome(lines: List[str]) -> Tuple[float, Optional[float]]:
        raw = sum(inv[k] for k in lines)
        return round(raw / total, 4), (round(1 / raw, 2) if len(lines) == 1 else None)

    p1_sweep, p2_sweep = f"{win}:0", f"0:{win}"
    long_ = [k for k in keys if k not in (p1_sweep, p2_sweep)]
    return {
        "p1": {"unSet": outcome([k for k in keys if k != p2_sweep]), "sinCeder": outcome([p1_sweep])},
        "p2": {"unSet": outcome([k for k in keys if k != p1_sweep]), "sinCeder": outcome([p2_sweep])},
        "match": {"largo": outcome(long_), "corridos": outcome([p1_sweep, p2_sweep])},
        "bestOf": 5 if bo5 else 3,
    }


def _estimated_price(fair: float, margin: float) -> float:
    """A price for an outcome the bookmaker quotes elsewhere: its fair odds with one margin on top."""
    return round(max(1.01, 1 / (fair * margin)), 2)


def _best_price(books: Any, side: str, reference: float) -> Dict[str, Any]:
    """Highest price among the collected bookmakers for one side, and whether it needs checking."""
    prices = sorted(
        ((float(v[side]), book) for book, v in (books or {}).items()
         if isinstance(v, dict) and v.get(side) and float(v[side]) > 1),
        reverse=True,
    )
    if not prices or prices[0][0] <= reference:
        return {"bestOdds": reference, "bestBook": None, "bestNeedsCheck": False}
    best, book = prices[0]
    return {"bestOdds": best, "bestBook": book, "bestNeedsCheck": best / reference - 1 > STALE_GAP}


def likely_picks(m: Dict[str, Any], history: Optional[Dict[str, Dict[str, Any]]] = None,
                 band_of=None, books: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
    """Most likely bets of an upcoming match, or None when it has no price yet.

    `books` is extra_data["odds_lines"]["books"] ({matchWinner|set1Winner: {book: {p1, p2}}}):
    the best price there rides along for the combo builder.
    """
    if m.get("status") != "SCHEDULED":
        return None
    markets = m.get("oddsMarkets") or {}
    names = {"p1": m.get("player1"), "p2": m.get("player2")}
    picks: List[Dict[str, Any]] = []
    mw = _pair(markets.get("matchWinner"))
    margin = (1 / mw[0] + 1 / mw[1]) if mw else DEFAULT_MARGIN

    def add(kind: str, label: str, prob: float, odds: Optional[float], direct: bool, note: Optional[str] = None,
            best: Optional[Dict[str, Any]] = None):
        if prob < MIN_PROB or not odds:
            return
        band = band_of(prob) if band_of else None
        past = ((history or {}).get(HISTORY_KEY[kind]) or {}).get(band or "")
        if past and kind not in PRICED_HISTORY:
            # Measured without a real price: only how often it came in counts.
            past = {k: past[k] for k in ("n", "winRate", "expected") if k in past}
        picks.append({
            "kind": kind,
            "label": label,
            "probability": round(prob, 4),
            "odds": odds,
            "oddsKind": "directa" if direct else "aprox",
            "payPer100": round((odds - 1) * 100),
            "lossProbability": round(1 - prob, 4),
            "note": note,
            "band": band,
            "history": past,
            **(best or {"bestOdds": odds, "bestBook": None, "bestNeedsCheck": False}),
        })

    for kind, key, what in (("partido", "matchWinner", "gana el partido"), ("set1", "set1Winner", "gana el 1er set")):
        pair = _pair(markets.get(key))
        if not pair:
            continue
        a, b = 1 / pair[0], 1 / pair[1]
        for side, price, inv in (("p1", pair[0], a), ("p2", pair[1], b)):
            add(kind, f"{names[side]} {what}", inv / (a + b), price, True,
                best=_best_price((books or {}).get(key), side, price))

    board = board_outcomes(markets.get("setBetting"))
    one_set = markets.get("oneSet") or {}
    win = 3 if board and board["bestOf"] == 5 else 2
    for side in ("p1", "p2"):
        quoted = one_set.get(side) or {}
        try:
            yes, no = float(quoted["yes"]), float(quoted["no"])
        except (KeyError, TypeError, ValueError):
            yes = no = None
        label = f"{names[side]} gana al menos un set"
        if yes and no and yes > 1 and no > 1:
            add("unSet", label, (1 / yes) / (1 / yes + 1 / no), yes, True,
                "Mercado «Gana al menos un set» (= hándicap +1.5 sets).")
        elif board:
            fair = board[side]["unSet"][0]
            add("unSet", label, fair, _estimated_price(fair, margin), False,
                "Se apuesta como hándicap +1.5 sets o «Gana al menos un set»; cuota estimada, confírmala en la casa.")
    if board:
        for side in ("p1", "p2"):
            fair, price = board[side]["sinCeder"]
            add("sinCeder", f"{names[side]} gana {win}-0", fair, price, True)
        fair = board["match"]["corridos"][0]
        add("sets", f"Se decide en {win} sets (sin set decisivo)", fair, _estimated_price(fair, margin), False,
            f"Se apuesta como Menos de {win + 0.5} sets; cuota estimada, confírmala en la casa.")
        fair = board["match"]["largo"][0]
        add("sets", "Se va a 3 sets" if win == 2 else "Dura 4 sets o más", fair, _estimated_price(fair, margin), False,
            f"Se apuesta como Más de {win + 0.5} sets; cuota estimada, confírmala en la casa.")

    if not picks:
        return None
    picks.sort(key=lambda p: -p["probability"])
    return picks[:MAX_PICKS]
