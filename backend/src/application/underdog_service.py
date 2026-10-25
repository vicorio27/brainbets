"""The case for betting the underdog of an upcoming tennis match.

When the user doubts the favourite, the app lists the data-backed arguments
there are for the other player ("es posible que le apuestes a X, ya que: ...").
Each argument says how much it has been worth when measured, because none of
them has beaten the closing price in our studies: this is information to
weigh, not a value signal. Pure function over the TennisMatch fields.
"""
from typing import Any, Dict, List, Optional

MODEL_GAP = 0.05        # a model has to give the underdog 5+ points more than the price
FORM_GAP = 0.10         # last-20 win rate gap that counts as "better form"
LOAD_GAP = 2            # extra matches in the last 7 days that count as "more load"
LAYOFF_DAYS = 45        # same threshold as the engine's layoff adjustment
TIEBREAK_HIGH = 0.40
DECIDER_HIGH = 0.40

SURFACE_ES = {"hard": "cemento", "clay": "arcilla", "grass": "césped"}


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


def underdog_case(m: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """{underdog, favorite, side, marketProb, odds, set1Odds, reasons, note} or None.

    None when the match is not upcoming or has no match-winner price. Each
    reason: {key, text, evidence}; `evidence` says what the data showed when
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

    s1 = markets.get("set1Winner") or {}
    return {
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
