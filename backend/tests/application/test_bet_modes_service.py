"""Conservative / risky picks (bet_modes_service)."""
from src.application import bet_modes_service as bm


def pick(kind, side, prob, odds, label=None):
    return {"kind": kind, "selector": {"side": side}, "probability": prob, "odds": odds,
            "label": label or f"{side} {kind}", "source": "casa", "oddsKind": "directa"}


def match(mid, picks, case=None):
    return {"matchId": mid, "player1": "A", "player2": "B", "status": "SCHEDULED",
            "likelyPicks": picks, "underdogCase": case}


def test_conservative_takes_the_safest_priced_bet():
    m = match("M1", [pick("partido", "p1", 0.86, 1.12), pick("unSet", "p1", 0.95, 1.03)])
    c = bm.conservative_for(m)
    assert c["kind"] == "unSet" and c["level"] == "muy segura" and not c["backed"]


def test_nothing_conservative_below_the_safe_line():
    assert bm.conservative_for(match("M1", [pick("partido", "p1", 0.70, 1.35)])) is None


def test_price_alone_is_never_a_risky_pick():
    case = {"side": "p2", "underdog": "B", "reasons": [{"key": "points_model", "text": "modelo"}],
            "options": [{"market": "partido", "odds": 2.4, "marketProb": 0.4}]}
    assert bm.risky_for(match("M1", [], case)) is None


def test_backed_underdog_gives_a_risky_pick_and_its_safe_version():
    case = {"side": "p2", "underdog": "Jodar", "reasons": [{"key": "h2h", "text": "Gana el cara a cara 2-0.", "market": "partido"}],
            "options": [{"market": "partido", "odds": 2.4, "marketProb": 0.41}]}
    m = match("M1", [pick("unSet", "p2", 0.71, 1.33), pick("unSet", "p1", 0.80, 1.20)], case)
    r = bm.risky_for(m)
    assert r["label"] == "Jodar gana el partido" and r["odds"] == 2.4
    assert r["safeVersion"]["kind"] == "unSet" and r["safeVersion"]["selector"] == {"side": "p2"}
    assert bm.conservative_for(m)["backed"]


def test_combos_pair_different_matches_safest_first():
    ms = [match("M1", [pick("unSet", "p1", 0.94, 1.05)]), match("M2", [pick("unSet", "p1", 0.86, 1.10)]),
          match("M3", [pick("unSet", "p2", 0.78, 1.20)])]
    out = bm.build_modes(ms)
    top = out["conservative"]["combos"][0]
    assert [l["matchId"] for l in top["legs"]] == ["M1", "M2"]
    assert top["odds"] == round(1.05 * 1.10, 3)
    assert all(len({l["matchId"] for l in c["legs"]}) == 2 for c in out["conservative"]["combos"])


def test_both_players_get_their_own_perspective():
    m = match("M1", [pick("unSet", "p1", 0.90, 1.08, "A gana al menos un set"), pick("partido", "p1", 0.72, 1.30, "A gana el partido"),
                     pick("unSet", "p2", 0.55, 1.65, "B gana al menos un set")])
    m["oddsMarkets"] = {"matchWinner": {"p1": 1.30, "p2": 3.40}}
    m["h2hDetail"] = {"p1Wins": 0, "p2Wins": 3, "meetings": []}
    view = bm.perspectives(m)
    a, b = view["sides"]
    assert a["favourite"] and not b["favourite"]
    assert a["conservative"]["label"] == "A gana al menos un set" and a["risky"] is None
    assert b["risky"]["label"] == "B gana el partido" and b["risky"]["odds"] == 3.40
    assert any("cara a cara 3-0" in r["text"] for r in b["reasons"])
    # B's set is 55%: below the backed line, so it stays a plain (not backed) safe version
    assert b["conservative"]["backed"] is False


def test_a_backed_favourite_also_gets_a_risky_straight_pick():
    m = match("M1", [pick("unSet", "p1", 0.90, 1.08)])
    m["oddsMarkets"] = {"matchWinner": {"p1": 1.60, "p2": 2.40}}
    m["h2hDetail"] = {"p1Wins": 2, "p2Wins": 0, "meetings": []}
    r = bm.risky_for_side(m, "p1")
    assert r and r["favourite"] and r["odds"] == 1.60
