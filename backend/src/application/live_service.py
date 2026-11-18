"""Reading a followed match from api-tennis get_livescore (pure, no DB, no network).

The feed says WHO won each point, not HOW: there is no shot or rally data. How a point ended is
deduced from the live counters (aces, double faults, winners, unforced errors) by comparing two
readings ~30 s apart: with one point in between it is exact; with several it is summarised.
Not measured against the price, and there are no live odds in the plan.
"""
from typing import Any, Dict, List, Optional

COUNTS = {"Aces": "aces", "Double Faults": "df", "Winners": "winners", "Unforced errors": "ue",
          "Last 10 balls": "last10"}
WON_TOTAL = {"1st serve points won": "first", "2nd serve points won": "second", "Net points won": "net",
             "Service Points Won": "servePts", "Return Points Won": "returnPts", "Total Points Won": "points",
             "Break Points Saved": "bpSaved", "Break Points Converted": "bpConv", "Service games won": "serveGames"}
MIN_POINTS = 20          # before this, no general conclusions
AGGRESSION_GAP = 0.05    # share of points ended by a winner or an unforced error
ACE_SHARE = 0.25         # share of his service points won with an ace: "lives off his serve"
FIRST_IN_GAP = 0.07      # first serves in, against his usual level
ERRORS_GAP = 5
HOT_LAST10 = 7


def _int(x: Any) -> Optional[int]:
    try:
        return int(str(x).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None


def _side(text: Any) -> Optional[str]:
    t = str(text or "").lower()
    return "p1" if t.startswith("first") else "p2" if t.startswith("second") else None


def parse_event(ev: Dict[str, Any]) -> Dict[str, Any]:
    """One live event -> {status, finished, sets, game, server, stats{p1,p2}, pointsPlayed, lastGame}."""
    keys = {str(ev.get("first_player_key")): "p1", str(ev.get("second_player_key")): "p2"}
    stats: Dict[str, Dict[str, Any]] = {"p1": {}, "p2": {}}
    for s in ev.get("statistics") or []:
        if s.get("stat_period") not in (None, "match"):
            continue
        side = keys.get(str(s.get("player_key")))
        if not side:
            continue
        name = s.get("stat_name")
        if name in COUNTS:
            v = _int(s.get("stat_value"))
            if v is not None:
                stats[side][COUNTS[name]] = v
        elif name in WON_TOTAL:
            w, t = _int(s.get("stat_won")), _int(s.get("stat_total"))
            if w is not None and t is not None:
                stats[side][WON_TOTAL[name]] = [w, t]
    sets = []
    for sc in ev.get("scores") or []:
        a, b = _int(sc.get("score_first")), _int(sc.get("score_second"))
        if a is not None and b is not None:
            sets.append([a, b])
    pbp = ev.get("pointbypoint") or []
    last = pbp[-1] if pbp else {}
    pts = [(stats[s].get("points") or [0, 0])[0] for s in ("p1", "p2")]
    status = str(ev.get("event_status") or "")
    return {
        "status": status,
        "finished": status.lower() in ("finished", "retired", "walk over", "cancelled") or bool(ev.get("event_winner")),
        "winner": _side(ev.get("event_winner")),
        "sets": sets,
        "setsWon": [str(ev.get("event_final_result") or "").split("-")[0].strip(),
                    (str(ev.get("event_final_result") or "").split("-") + [""])[1].strip()],
        "game": ev.get("event_game_result") if ev.get("event_game_result") not in (None, "-") else None,
        "server": _side(ev.get("event_serve")),
        "stats": stats,
        "pointsPlayed": sum(pts),
        "pointsWon": {"p1": pts[0], "p2": pts[1]},
        "games": len(pbp),
        "lastGame": {"set": last.get("set_number"), "game": last.get("number_game"),
                     "server": _side(last.get("player_served")), "lostServe": _side(last.get("serve_lost"))} if last else None,
    }


def set_done(a: int, b: int) -> bool:
    hi, lo = max(a, b), min(a, b)
    return (hi >= 6 and hi - lo >= 2) or (hi == 7 and lo in (5, 6))


def _d(cur: Dict[str, Any], prev: Dict[str, Any], side: str, key: str) -> int:
    return max(0, (cur["stats"][side].get(key) or 0) - (prev["stats"][side].get(key) or 0))


def point_events(prev: Optional[Dict[str, Any]], cur: Dict[str, Any], names: Dict[str, str]) -> List[str]:
    """What happened between two readings, in plain words."""
    if not prev:
        return []
    out = []
    n = cur["pointsPlayed"] - prev["pointsPlayed"]
    if n > 0:
        won = {s: cur["pointsWon"][s] - prev["pointsWon"][s] for s in ("p1", "p2")}
        d = {s: {k: _d(cur, prev, s, k) for k in ("aces", "df", "winners", "ue")} for s in ("p1", "p2")}
        if n == 1:
            w = "p1" if won["p1"] > 0 else "p2"
            l = "p2" if w == "p1" else "p1"
            W, L = names[w], names[l]
            if d[w]["aces"]:
                out.append(f"Ace de {W}.")
            elif d[l]["df"]:
                out.append(f"Doble falta de {L}: punto para {W}.")
            elif d[w]["winners"]:
                out.append(f"Winner de {W}: punto agresivo.")
            elif d[l]["ue"]:
                out.append(f"Error no forzado de {L}: punto regalado a {W}.")
            else:
                out.append(f"Punto para {W} (error forzado o peloteo largo).")
        else:
            parts = []
            for s in ("p1", "p2"):
                bits = [f"{v} {lbl}" for v, lbl in ((d[s]["aces"], "ace(s)"), (d[s]["winners"], "winner(s)"),
                                                    (d[s]["ue"], "error(es) no forzado(s)"), (d[s]["df"], "doble(s) falta(s)")) if v]
                parts.append(f"{names[s]} ganó {won[s]}" + (f" ({', '.join(bits)})" if bits else ""))
            out.append(f"Últimos {n} puntos: " + "; ".join(parts) + ".")
    g = cur.get("lastGame")
    if g and g != prev.get("lastGame") and g.get("lostServe"):
        lost = g["lostServe"]
        other = "p2" if lost == "p1" else "p1"
        out.append(f"¡Break! {names[other]} le quebró el saque a {names[lost]} ({g.get('set')}, game {g.get('game')}).")
    if len(cur["sets"]) > len(prev["sets"]):
        # the feed may list only finished sets, or the one in play too: take the newest finished one
        done = [x for x in cur["sets"] if set_done(*x)]
        a, b = done[-1] if done else (0, 0)
        if done:
            out.append(f"Set para {names['p1'] if a > b else names['p2']} ({a}-{b}).")
    if cur["finished"] and not prev.get("finished"):
        out.append(f"Terminó: ganó {names.get(cur.get('winner')) or '?'}.")
    return out


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def general_read(cur: Dict[str, Any], names: Dict[str, str], usual: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, Any]:
    """Conclusions over the whole match so far. `usual`: {p1: {firstIn, aces}} from form_service."""
    played = cur["pointsPlayed"]
    if played < MIN_POINTS:
        return {"points": played, "items": [f"Muy pronto para sacar conclusiones ({played} puntos jugados)."]}
    st = cur["stats"]
    items: List[str] = []
    has_shots = all("winners" in st[s] and "ue" in st[s] for s in ("p1", "p2"))
    if has_shots:
        agg = {s: (st[s]["winners"] + st[s]["ue"]) / played for s in ("p1", "p2")}
        hi = "p1" if agg["p1"] >= agg["p2"] else "p2"
        lo = "p2" if hi == "p1" else "p1"
        if agg[hi] - agg[lo] >= AGGRESSION_GAP:
            items.append(f"{names[hi]} está siendo más agresivo: el {_pct(agg[hi])} de los puntos terminan en winner o error suyo "
                         f"({names[lo]}: {_pct(agg[lo])}).")
        else:
            items.append(f"Los dos arriesgan parecido ({names['p1']} {_pct(agg['p1'])}, {names['p2']} {_pct(agg['p2'])} "
                         "de los puntos terminan en winner o error suyo).")
        for s in ("p1", "p2"):
            w, e = st[s]["winners"], st[s]["ue"]
            if w + e >= 8:
                if w >= e * 1.3:
                    items.append(f"A {names[s]} le funciona: {w} winners por {e} errores no forzados.")
                elif e >= w * 1.3:
                    items.append(f"A {names[s]} le está costando: {e} errores no forzados y {w} winners.")
        if abs(st["p1"]["ue"] - st["p2"]["ue"]) >= ERRORS_GAP:
            more = "p1" if st["p1"]["ue"] > st["p2"]["ue"] else "p2"
            items.append(f"{names[more]} lleva {abs(st['p1']['ue'] - st['p2']['ue'])} errores no forzados más.")
    for s in ("p1", "p2"):
        sp = st[s].get("servePts")
        if sp and sp[0] >= 10 and (st[s].get("aces") or 0) / sp[0] >= ACE_SHARE:
            items.append(f"{names[s]} vive del saque: gana el {_pct(st[s]['aces'] / sp[0])} de sus puntos de saque con ace.")
        f, sec = st[s].get("first"), st[s].get("second")
        if f and sec and f[1] + sec[1] >= 15:
            first_in = f[1] / (f[1] + sec[1])
            base = ((usual or {}).get(s) or {}).get("firstIn")
            if base is not None and abs(first_in - base) >= FIRST_IN_GAP:
                word = "más" if first_in > base else "menos"
                items.append(f"{names[s]} mete {word} primeros de lo normal: {_pct(first_in)} (lo normal en él: {_pct(base)}).")
        net = st[s].get("net")
        if net and net[1] >= 8:
            items.append(f"{names[s]} sube a la red: {net[0]} de {net[1]} puntos ganados allí.")
        if (st[s].get("last10") or 0) >= HOT_LAST10:
            items.append(f"{names[s]} tiene el impulso: ganó {st[s]['last10']} de los últimos 10 puntos.")
        bp = st[s].get("bpSaved")
        if bp and bp[1] >= 3:
            items.append(f"{names[s]} enfrentó {bp[1]} puntos de break y salvó {bp[0]}.")
    if not has_shots:
        items.append("El feed no trae winners ni errores no forzados de este partido: la agresividad no se puede medir.")
    return {"points": played, "items": items}
