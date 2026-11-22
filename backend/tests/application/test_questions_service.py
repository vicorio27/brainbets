from src.application.questions_service import build_questions, history, serve, tired, why_favourite


def base(**kw):
    d = {"p1": "Zverev A.", "p2": "Alcaraz C.", "surface": "hard"}
    d.update(kw)
    return d


def test_nothing_without_data_and_one_broken_rule_does_not_hide_the_rest():
    assert build_questions(base()) == []
    got = build_questions(base(odds={"matchWinner": {"p1": 2.92, "p2": 1.46}}, tload="roto"))
    assert [q["id"] for q in got] == ["favourite"]


def test_tired_names_who_carries_more_games():
    d = base(tload={"players": [
        {"side": "player1", "matchesPlayed": 4, "totalGames": 87, "loadLevel": "alta"},
        {"side": "player2", "matchesPlayed": 4, "totalGames": 82, "loadLevel": "alta"}]},
        sload={"players": [{"side": "player1", "restDays": 1, "totalMatches": 9, "totalGames": 208},
                           {"side": "player2", "restDays": 1, "totalMatches": 13, "totalGames": 289}]})
    q = tired(d)
    assert q["hint"] == "Zverev 87 games · Alcaraz 82 · Zverev lleva 5 más"
    assert "descansó 1 día" in q["lines"][0] and "13 partidos y 289 games en 30 días" in q["lines"][1]


def test_favourite_uses_the_price_without_margin_and_flags_a_worse_ranking():
    q = why_favourite(base(odds={"matchWinner": {"p1": 2.92, "p2": 1.46}}, rank=(1, 3),
                           h2h={"p1Wins": 6, "p2Wins": 7, "meetings": [{"date": "2026-01-01"}]}))
    assert q["hint"] == "Alcaraz 67%"
    assert "pese a tener peor ranking" in q["lines"][1]
    assert "a favor de Alcaraz C." in q["lines"][2]
    assert why_favourite(base(odds={"matchWinner": {"p1": 0, "p2": 0}})) is None


def test_serve_reads_hold_from_the_level_metrics_and_the_first_game():
    lv = {"level": "mixto", "headline": "x", "metrics": [
        {"key": "hold", "recent": 0.9615, "base": 0.9231, "recentSample": 5},
        {"key": "break", "recent": 0.1154, "base": 0.1875, "recentSample": 5}]}
    q = serve(base(levels=[lv, None], firstGame={"p1": {"text": "Sacando primero defendió 36 de 39 (92%)"}}))
    assert q["hint"] == "Zverev 96%"
    assert "juegos de saque ganados 96% en sus últimos 5 (lo normal en él: 92%)" in q["lines"][0]
    assert "sacando primero defendió 36 de 39 (92%)" in q["lines"][0]


def test_history_quotes_how_often_a_similar_bet_came_out():
    q = history(base(picks=[{"label": "Alcaraz C. gana al menos un set", "probability": 0.83, "band": "80-90",
                              "history": {"winRate": 0.85, "n": 1207, "expected": 0.83, "yield": None}}]))
    assert q["hint"] == "Alcaraz C. gana al menos un set: 85% de 1207"
    assert history(base(picks=[{"label": "x", "history": None}])) is None
