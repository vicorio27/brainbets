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
