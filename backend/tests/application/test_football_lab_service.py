import random

from src.application import football_lab_service as fl


def row(day, p_market, p_model, won):
    return {"date": day, "x": [fl.lab._logit(p_model) - fl.lab._logit(p_market)], "won": won,
            "pMarket": p_market, "pModel": p_model, "odds1": 1.9, "odds2": 1.95}


def test_fair_over_takes_the_margin_out():
    assert round(fl.fair_over(1.9, 1.9), 3) == 0.5
    assert round(fl.fair_over(1.8, 2.1), 3) == 0.538
    assert fl.fair_over(None, 2.0) is None and fl.fair_over(1.0, 2.0) is None


def test_market_check_compares_price_model_and_result():
    rows = [row("2026-11-24", 0.6, 0.7, 1), row("2026-11-24", 0.4, 0.3, 0)]
    c = fl.market_check(rows)
    assert c == {"matches": 2, "marketOver": 0.5, "modelOver": 0.5, "actualOver": 0.5}
    assert fl.market_check([]) == {"matches": 0}


def test_a_small_sample_only_gathers():
    rows = [row("2026-11-24", 0.55, 0.6, 1)] * 10
    r = fl.build_report(rows)
    assert r["verdict"]["level"] == "juntando_muestra" and r["weights"] is None
    assert r["postFreeze"].get("matches", 0) == 0


def test_a_model_with_no_information_is_not_proven():
    rnd = random.Random(7)
    rows = []
    for i in range(400):
        pm = rnd.uniform(0.35, 0.65)
        rows.append(row(f"2026-12-{1 + i // 20:02d}" if i < 400 else "", pm, min(0.9, max(0.1, pm + rnd.uniform(-0.1, 0.1))),
                        1 if rnd.random() < pm else 0))
    r = fl.build_report(rows)
    assert r["verdict"]["level"] in ("no_demostrado", "descartado", "juntando_muestra")
    assert r["verdict"]["level"] != "demostrado"
    assert r["weights"][0]["feature"] == "model"
