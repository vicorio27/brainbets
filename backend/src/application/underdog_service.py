"""The case for betting the underdog of an upcoming tennis match.

When the user doubts the favourite, the app lists the data-backed arguments
there are for the other player ("es posible que le apuestes a X, ya que: ...").
Each argument says how much it has been worth when measured, because none of
them has beaten the closing price in our studies: this is information to
weigh, not a value signal. Pure function over the TennisMatch fields.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

MODEL_GAP = 0.05        # a model has to give the underdog 5+ points more than the price
FORM_GAP = 0.10         # last-20 win rate gap that counts as "better form"
LOAD_GAP = 2            # extra matches in the last 7 days that count as "more load"
LAYOFF_DAYS = 45        # same threshold as the engine's layoff adjustment
TIEBREAK_HIGH = 0.40
DECIDER_HIGH = 0.40

SURFACE_ES = {"hard": "cemento", "clay": "arcilla", "grass": "césped"}
FINAL_DROUGHT_YEARS = 2  # the drought the finals study measured (research_finals.py)

# What each argument would support: winning the match, the first set, or one set.
MARKET_OF = {"points_model": "partido", "surface_elo": "partido", "h2h": "partido", "h2h_last": "partido",
             "form": "partido", "load": "partido", "layoff": "partido", "news_fav": "partido",
             "news_dog": "partido", "tiebreak": "unSet", "decider": "unSet", "streak": "set1",
             "final_drought": "set1", "first_final": "set1"}
VERB = {"partido": "ganarle el partido", "set1": "ganarle el primer set", "unSet": "sacarle un set"}
# api-tennis also labels some qualifying matches "<event> - Final": a real final is the
# last match of its event (nothing of the same league in the next days)...
FINAL_SQL = """((m.extra_data->>'round' = 'The Final' or m.extra_data->>'round' like '%% - Final')
    and not exists (select 1 from matches m2 where m2.league_id = m.league_id
                    and m2.match_date > m.match_date + interval '2 hours'
                    and m2.match_date < m.match_date + interval '5 days'))"""
# ...and an upcoming one comes after a draw's worth of matches of that event.
MIN_EVENT_MATCHES_BEFORE_FINAL = 8


def is_final(round_name: Optional[str]) -> bool:
    r = (round_name or "").strip()
    return r == "The Final" or r.endswith(" - Final")


def finals_history(db: Session, matches: List[Any]) -> Dict[Any, Dict[str, Any]]:
    """{match.id: {"p1": {lastFinal, firstSeen}, "p2": {...}}} for upcoming finals.

    lastFinal: date of the player's previous final in our data (None = none);
    firstSeen: his first match in our data (to tell "never" from "no data").
    """
    todo = []
    for m in matches:
        if m.status != "SCHEDULED" or not is_final((m.extra_data or {}).get("round")) or not m.match_date:
            continue
        sides = {c.side: c.competitor_id for c in (m.competitors or [])}
        if not (sides.get("player1") and sides.get("player2")):
            continue
        before = db.execute(text("""select count(*) from matches where league_id = :l
            and match_date < :d and match_date > :d - interval '10 days'"""),
                            {"l": m.league_id, "d": m.match_date}).scalar()
        if before >= MIN_EVENT_MATCHES_BEFORE_FINAL:
            todo.append((m, sides))
    out: Dict[Any, Dict[str, Any]] = {}
    for m, sides in todo:
        ids = [str(sides["player1"]), str(sides["player2"])]
        rows = db.execute(text(f"""
            select mc.competitor_id::text,
                   max(m.match_date) filter (where {FINAL_SQL}),
                   min(m.match_date)
            from match_competitors mc join matches m on m.id = mc.match_id
            where mc.competitor_id = any(cast(:ids as uuid[])) and m.match_date < :d and m.status = 'FINISHED'
            group by 1"""), {"ids": ids, "d": m.match_date}).fetchall()
        by = {r[0]: {"lastFinal": r[1].date().isoformat() if r[1] else None,
                     "firstSeen": r[2].date().isoformat() if r[2] else None} for r in rows}
        out[m.id] = {"p1": by.get(ids[0]), "p2": by.get(ids[1])}
    return out


def _years_between(a: str, b: str) -> float:
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).days / 365.25


def _fair(odds: Dict[str, Any]) -> Optional[float]:
    """Player1's no-margin probability from a {p1, p2} price pair."""
    try:
        a, b = 1 / float(odds["p1"]), 1 / float(odds["p2"])
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None
    return a / (a + b)


def _elo_prob(r_a: Optional[float], r_b: Optional[float]) -> Optional[float]:
    if r_a is None or r_b is None:
        return None
    return 1 / (1 + 10 ** ((r_b - r_a) / 400))


def _pct(p: float) -> str:
    return f"{round(p * 100)}%"


def _one_set(board: Dict[str, Any], model: Dict[str, Any], u: str) -> Optional[Dict[str, Any]]:
    """P(underdog wins at least one set) = 1 - P(favourite wins in straight sets).

    `board` is the bookmaker's set-betting prices keyed "2:0" from player1's side,
    `model` the point model's set scores keyed "2-0" from player1's side.
    """
    bo5 = "3:0" in board or "0:3" in board or "3-0" in model
    straight = ("0:3" if bo5 else "0:2") if u == "p1" else ("3:0" if bo5 else "2:0")
    out: Dict[str, Any] = {"marketProb": None, "modelProb": None}
    try:
        inv = {k: 1 / float(v) for k, v in board.items() if float(v) > 1}
        if straight in inv and len(inv) >= (6 if bo5 else 4):
            out["marketProb"] = round(1 - inv[straight] / sum(inv.values()), 4)
    except (TypeError, ValueError):
        pass
    if model.get(straight.replace(":", "-")) is not None:
        out["modelProb"] = round(1 - model[straight.replace(":", "-")], 4)
    return out if out["marketProb"] is not None or out["modelProb"] is not None else None


def underdog_case(m: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """{headline, options, underdog, favorite, side, marketProb, odds, set1Odds, reasons, note} or None.

    None when the match is not upcoming or has no match-winner price. Each
    reason: {key, text, evidence, market}; `market` is what it would support
    (partido / set1 / unSet), `options` the prices of those three bets. `evidence` says what the data showed when
    this kind of argument was measured (or that it has not been measured).
    """
    if m.get("status") not in (None, "SCHEDULED"):
        return None
    markets = m.get("oddsMarkets") or {}
    mw = markets.get("matchWinner") or {}
    q1 = _fair(mw)
    if q1 is None or abs(q1 - 0.5) < 1e-9:
        return None
    u = "p2" if q1 > 0.5 else "p1"          # the underdog's side
    f = "p1" if u == "p2" else "p2"
    names = {"p1": m.get("player1"), "p2": m.get("player2")}
    num = {"p1": "1", "p2": "2"}
    qu = q1 if u == "p1" else 1 - q1
    U, F = names[u], names[f]
    feats = m.get("features") or {}
    fu, ff = feats.get("player" + num[u]) or {}, feats.get("player" + num[f]) or {}
    reasons: List[Dict[str, str]] = []

    def add(key, text, evidence):
        reasons.append({"key": key, "text": text, "evidence": evidence})

    # 1. Serve/return point model sees the match closer than the price.
    g = (m.get("gamesModel") or {}).get("markets") or {}
    if g.get("matchP1") is not None:
        pu = g["matchP1"] if u == "p1" else 1 - g["matchP1"]
        if pu - qu >= MODEL_GAP:
            add("points_model",
                f"El modelo de saque y resto le da {_pct(pu)} de ganar; la casa, {_pct(qu)}.",
                "Probado en 2.272 partidos de 2026: no le ganó a la cuota (la casa acertó más).")

    # 2. Surface Elo sees the match closer than the price.
    eu, ef = m.get("eloSurfacePlayer" + num[u]), m.get("eloSurfacePlayer" + num[f])
    pe = _elo_prob(eu, ef)
    if pe is not None and pe - qu >= MODEL_GAP:
        surf = SURFACE_ES.get(m.get("surface"), m.get("surface") or "esta superficie")
        add("surface_elo",
            f"Por su Elo en {surf} ({round(eu)} contra {round(ef)}) tendría {_pct(pe)}, más que el {_pct(qu)} de la casa.",
            "El Elo solo acierta menos que la cuota (65.0% contra 66.7% en 123 partidos con cuota previa).")

    # 3. Head-to-head in the underdog's favour.
    h = m.get("h2hDetail") or {}
    wu, wf = h.get(u + "Wins") or 0, h.get(f + "Wins") or 0
    meetings = h.get("meetings") or []
    if wu > wf and wu + wf >= 2:
        add("h2h", f"Gana el cara a cara {wu}-{wf}.",
            "No medido como señal propia; la casa conoce el historial y suele ponerlo en el precio.")
    elif meetings and meetings[0].get("winner") == u:
        last = meetings[0]
        add("h2h_last",
            f"Ganó el último partido entre ellos ({last.get('tournament') or '?'} {str(last.get('date') or '')[:4]}"
            f"{', ' + last['sets'] if last.get('sets') else ''}).",
            "No medido como señal propia; la casa conoce el historial.")

    # 4. Better recent form.
    ru = (fu.get("last_20") or {}).get("win_rate")
    rf = (ff.get("last_20") or {}).get("win_rate")
    if ru is not None and rf is not None and ru - rf >= FORM_GAP:
        add("form", f"Viene mejor: ganó {_pct(ru)} de sus últimos 20 partidos, {F} {_pct(rf)}.",
            "La forma ya entra en el motor y en la cuota; sola no le ha ganado al precio.")

    # 5. The favourite carries more load or comes back from a layoff.
    lu, lf = fu.get("matches_last_7_days"), ff.get("matches_last_7_days")
    if lu is not None and lf is not None and lf - lu >= LOAD_GAP:
        add("load", f"{F} jugó {lf} partidos en los últimos 7 días; {U}, {lu}.",
            "No medido todavía contra la cuota.")
    df = ff.get("days_since_last_match")
    if df is not None and df >= LAYOFF_DAYS:
        add("layoff", f"{F} no juega hace {df} días: vuelve de un parón.",
            "El motor ya lo descuenta (hasta 6 puntos); el ranking tarda en reflejarlo.")

    # 6. News: bad for the favourite, good for the underdog.
    news = m.get("playerNews") or {}
    for it in news.get("player" + num[f]) or []:
        if it.get("impact") == "negativo":
            add("news_fav", f"Noticia en contra de {F}: {it.get('note') or it.get('headline')}",
                "Titular de prensa: puede que la casa ya lo tenga, o no. Leer la nota.")
    for it in news.get("player" + num[u]) or []:
        if it.get("impact") == "positivo":
            add("news_dog", f"Noticia a favor de {U}: {it.get('note') or it.get('headline')}",
                "Titular de prensa: puede que la casa ya lo tenga, o no. Leer la nota.")

    # 7. Tight match profile: tiebreaks and deciding sets add variance.
    gm = m.get("gamesModel") or {}
    if (gm.get("tiebreak") or 0) >= TIEBREAK_HIGH:
        add("tiebreak", f"Partido de saques: {_pct(gm['tiebreak'])} de que haya al menos un tiebreak, y un tiebreak es casi una moneda.",
            "Más azar no cambia quién es favorito, pero hace más probable que el no favorito gane un set.")
    if (gm.get("decider") or 0) >= DECIDER_HIGH:
        add("decider", f"{_pct(gm['decider'])} de que se vaya al set decisivo.",
            "Información para el primer set o el total de sets, no para el ganador.")

    # 8. Tournament streak: shown, but the study says it is already priced.
    st = m.get("streakPlayer" + num[u]) or {}
    if (st.get("wins") or 0) >= 2:
        add("streak", f"Lleva {st['wins']} victorias en este torneo.",
            "Estudio 2010–2020: el no favorito en racha gana lo que dice la cuota (29.3% contra 29.2%), "
            "y con ranking peor que 100 gana menos. La racha ya está en el precio.")

    # 9. A final after a long drought (or his first one): the motivation argument.
    fh = (m.get("finalsHistory") or {}).get(u) or {}
    day = m.get("eventDate")
    if is_final(m.get("round")) and fh.get("firstSeen") and day:
        seen = _years_between(fh["firstSeen"], day)
        if fh.get("lastFinal") is None and seen >= 2:
            add("first_final", f"Es la primera final de {U} en los partidos que tenemos (desde {fh['firstSeen'][:4]}).",
                "Estudio 2010–2020 (68 finales): en su primera final el no favorito ganó 26.5% contra 29.9% de la cuota, "
                "y el primer set 26.5%: los nervios pesan más que la motivación.")
        elif fh.get("lastFinal"):
            gap = _years_between(fh["lastFinal"], day)
            if gap >= FINAL_DROUGHT_YEARS:
                add("final_drought",
                    f"Es su primera final desde {fh['lastFinal'][:4]} (hace {int(gap)} años): puede salir con todo.",
                    "Estudio 2010–2020 (105 finales): el no favorito sin final en 2+ años ganó 32.4% contra 32.0% de la cuota "
                    "y el primer set menos de lo esperado; con 4+ años, 27.9% contra 32.9% (43 finales). "
                    "La motivación no se ha visto en el resultado.")

    for r in reasons:
        r["market"] = MARKET_OF.get(r["key"], "partido")

    s1 = markets.get("set1Winner") or {}
    q_s1 = _fair(s1)
    options = [{"market": "partido", "label": "Ganar el partido", "odds": mw.get(u), "marketProb": round(qu, 4),
                "modelProb": None}]
    if g.get("matchP1") is not None:
        options[0]["modelProb"] = round(g["matchP1"] if u == "p1" else 1 - g["matchP1"], 4)
    if q_s1 is not None:
        options.append({"market": "set1", "label": "Ganar el primer set", "odds": s1.get(u),
                        "marketProb": round(q_s1 if u == "p1" else 1 - q_s1, 4),
                        "modelProb": (round(g["set1P1"] if u == "p1" else 1 - g["set1P1"], 4)
                                      if g.get("set1P1") is not None else None)})
    one = _one_set(markets.get("setBetting") or {}, g.get("setScores") or {}, u)
    if one:
        options.append({"market": "unSet", "label": "Sacarle al menos un set", "odds": None, **one})

    wanted = [k for k in ("partido", "set1", "unSet") if any(r["market"] == k for r in reasons)]
    headline = None
    if wanted:
        verbs = [VERB[k] for k in wanted]
        joined = verbs[0] if len(verbs) == 1 else ", ".join(verbs[:-1]) + " o " + verbs[-1]
        headline = f"{U} podría {joined} a {F}, ya que:"
    return {
        "headline": headline,
        "options": options,
        "side": u,
        "underdog": U,
        "favorite": F,
        "marketProb": round(qu, 4),
        "odds": mw.get(u),
        "set1Odds": s1.get(u),
        "reasons": reasons,
        "note": ("Ninguno de estos argumentos le ha ganado a la cuota cuando se midió: "
                 "cuando nuestros números discrepan de la casa, la casa suele acertar más. "
                 "Si apuestas al no favorito, que sea con poco dinero."),
    }
