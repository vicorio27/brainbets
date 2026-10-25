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


def test_headline_names_the_bets_the_arguments_support():
    c = underdog_case(_match(
        h2hDetail={"p1Wins": 4, "p2Wins": 2, "meetings": [{"winner": "p1"}]},
        gamesModel={"tiebreak": 0.45, "markets": {}},
    ))
    assert c["headline"] == "Musetti L. podría ganarle el partido o sacarle un set a Fritz T., ya que:"
    assert [r["market"] for r in c["reasons"]] == ["partido", "unSet"]


def test_no_headline_without_arguments():
    assert underdog_case(_match())["headline"] is None


def test_options_carry_match_first_set_and_one_set_prices():
    c = underdog_case(_match(oddsMarkets={
        "matchWinner": {"p1": 2.67, "p2": 1.53}, "set1Winner": {"p1": 2.45, "p2": 1.6},
        "setBetting": {"2:0": 4.33, "2:1": 5, "1:2": 4, "0:2": 2.37},
    }, gamesModel={"markets": {"setScores": {"2-0": 0.257, "0-2": 0.37, "2-1": 0.17, "1-2": 0.2}}}))
    opts = {o["market"]: o for o in c["options"]}
    assert set(opts) == {"partido", "set1", "unSet"}
    assert opts["set1"]["odds"] == 2.45
    assert 0.60 < opts["unSet"]["marketProb"] < 0.64   # 1 - P(Fritz 2-0) without margin
    assert opts["unSet"]["modelProb"] == 0.63


def test_first_final_in_years_is_an_argument_with_the_study_attached():
    c = underdog_case(_match(
        player1="Medvedev D.", player2="Basilashvili N.", eventDate="2026-10-25", round="ATP Almaty - Final",
        oddsMarkets={"matchWinner": {"p1": 1.26, "p2": 4.3}},
        finalsHistory={"p1": {"lastFinal": "2026-05-01", "firstSeen": "2015-01-01"},
                       "p2": {"lastFinal": "2022-02-27", "firstSeen": "2012-01-01"}},
    ))
    r = c["reasons"][0]
    assert r["key"] == "final_drought" and r["market"] == "set1"
    assert "desde 2022" in r["text"] and "105 finales" in r["evidence"]
    assert c["headline"].startswith("Basilashvili N. podría ganarle el primer set")


def test_finals_argument_only_in_a_final():
    c = underdog_case(_match(round="ATP Lyon - Semi-finals", eventDate="2026-10-25",
                             finalsHistory={"p1": {"lastFinal": None, "firstSeen": "2015-01-01"}}))
    assert c["reasons"] == []
