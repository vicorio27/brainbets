from src.application.underdog_service import underdog_case


def _match(**over):
    m = {
        "status": "SCHEDULED",
        "player1": "Musetti L.",
        "player2": "Fritz T.",
        "surface": "hard",
        "oddsMarkets": {"matchWinner": {"p1": 2.67, "p2": 1.53}, "set1Winner": {"p1": 2.45, "p2": 1.6}},
    }
    m.update(over)
    return m


def test_underdog_is_the_side_with_the_higher_price():
    c = underdog_case(_match())
    assert c["side"] == "p1" and c["underdog"] == "Musetti L." and c["favorite"] == "Fritz T."
    assert c["odds"] == 2.67 and c["set1Odds"] == 2.45
    assert 0.35 < c["marketProb"] < 0.37
    assert c["reasons"] == []


def test_no_case_without_a_price_or_once_the_match_started():
    assert underdog_case(_match(oddsMarkets={})) is None
    assert underdog_case(_match(status="FINISHED")) is None


def test_head_to_head_and_point_model_count_for_the_underdog():
    c = underdog_case(_match(
        h2hDetail={"p1Wins": 4, "p2Wins": 2, "meetings": [{"winner": "p1"}]},
        gamesModel={"markets": {"matchP1": 0.43}},
    ))
    keys = [r["key"] for r in c["reasons"]]
    assert keys == ["points_model", "h2h"]
    assert all(r["evidence"] for r in c["reasons"])


def test_a_model_only_slightly_above_the_price_is_not_an_argument():
    c = underdog_case(_match(gamesModel={"markets": {"matchP1": 0.38}}))
    assert c["reasons"] == []


def test_load_layoff_and_news_against_the_favourite():
    c = underdog_case(_match(
        player1="Medvedev D.", player2="Basilashvili N.",
        oddsMarkets={"matchWinner": {"p1": 1.26, "p2": 4.3}},
        features={"player1": {"matches_last_7_days": 4, "days_since_last_match": 60},
                  "player2": {"matches_last_7_days": 1}},
        playerNews={"player1": [{"impact": "negativo", "note": "molestias en la espalda"}], "player2": []},
        streakPlayer2={"wins": 5},
    ))
    assert c["underdog"] == "Basilashvili N."
    assert [r["key"] for r in c["reasons"]] == ["load", "layoff", "news_fav", "streak"]
    assert "ya está en el precio" in c["reasons"][-1]["evidence"]
