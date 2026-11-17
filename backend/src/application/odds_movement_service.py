"""How the price of each upcoming match moved between collects (pure helpers).

`/matches/bulk` appends a snapshot of the main two-way prices to extra_data['odds_history'] every
time a collect brings a new price for a match that has not started (collect runs 03:00, 12:00 and
20:00 Bogota). There is no history before 2026-11-17.
"""
from typing import Any, Dict, List, Optional

MAX_SNAPSHOTS = 30
MOVE_POINTS = 0.03   # 3 points of fair probability: a move worth showing
BARGAIN_EDGE = 0.005  # a book at least 0.5% above the fair price


def snapshot(odds_markets: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    om = odds_markets or {}
    snap = {}
    for key in ("matchWinner", "set1Winner"):
        v = om.get(key) or {}
        if v.get("p1") and v.get("p2"):
            snap[key] = {"p1": v["p1"], "p2": v["p2"]}
    one = om.get("oneSet") or {}
    if one.get("p1") and one.get("p2"):
        snap["oneSet"] = {s: {"yes": (one[s] or {}).get("yes"), "no": (one[s] or {}).get("no")} for s in ("p1", "p2")}
    return snap or None


def append_snapshot(history: Optional[List[Dict[str, Any]]], odds_markets: Optional[Dict[str, Any]],
                    at: str) -> List[Dict[str, Any]]:
    """History plus this price, unless nothing changed since the last one."""
    hist = list(history or [])
    snap = snapshot(odds_markets)
    if not snap:
        return hist
    if hist and {k: v for k, v in hist[-1].items() if k != "at"} == snap:
        return hist
    hist.append({"at": at, **snap})
    return hist[-MAX_SNAPSHOTS:]


def _fair(a: Any, b: Any) -> Optional[float]:
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return None
    if a <= 1 or b <= 1:
        return None
    return (1 / a) / (1 / a + 1 / b)


def _side_prices(snap: Dict[str, Any], market: str, side: str):
    other = "p2" if side == "p1" else "p1"
    if market == "oneSet":
        v = (snap.get("oneSet") or {}).get(side) or {}
        return v.get("yes"), _fair(v.get("yes"), v.get("no"))
    v = snap.get(market) or {}
    return v.get(side), _fair(v.get(side), v.get(other))


def movement(history: Optional[List[Dict[str, Any]]], names: Dict[str, str]) -> List[Dict[str, Any]]:
    """First vs latest price of each side, with the change in fair probability."""
    hist = history or []
    if len(hist) < 2:
        return []
    first, last = hist[0], hist[-1]
    labels = {"matchWinner": "gana el partido", "set1Winner": "gana el 1er set", "oneSet": "gana al menos un set"}
    out = []
    for market, what in labels.items():
        for side in ("p1", "p2"):
            o0, f0 = _side_prices(first, market, side)
            o1, f1 = _side_prices(last, market, side)
            if f0 is None or f1 is None:
                continue
            delta = f1 - f0
            out.append({
                "market": market, "side": side, "label": f"{names.get(side)} {what}",
                "fromOdds": o0, "toOdds": o1, "fromProb": round(f0, 4), "toProb": round(f1, 4),
                "delta": round(delta, 4), "moved": abs(delta) >= MOVE_POINTS,
                "from": first.get("at"), "to": last.get("at"), "snapshots": len(hist),
            })
    return out
