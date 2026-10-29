from src.application.best_bets_service import band_of
from src.application.likely_picks_service import board_outcomes, likely_picks

BOARD = {"2:0": 1.57, "2:1": 3.75, "1:2": 8, "0:2": 10}


def _match(**over):
    m = {
        "status": "SCHEDULED", "player1": "Zverev A.", "player2": "Griekspoor T.",
        "oddsMarkets": {"matchWinner": {"p1": 1.2, "p2": 5.0}, "set1Winner": {"p1": 1.31, "p2": 3.6},
                        "setBetting": BOARD},
    }
    m.update(over)
    return m


def test_board_reads_at_least_one_set_and_straight_sets():
    b = board_outcomes(BOARD)
    fair, price = b["p2"]["unSet"]
    assert 0.40 < fair < 0.45 and price is None   # 1 - P(Zverev 2-0); several lines have no price
    assert b["p1"]["unSet"][0] > 0.90             # the favourite takes a set almost always
    assert b["p1"]["sinCeder"][1] == 1.57         # a single board line keeps its own price
    corridos, largo = b["match"]["corridos"][0], b["match"]["largo"][0]
    assert abs(corridos + largo - 1) < 1e-3


def test_incomplete_board_is_ignored():
    assert board_outcomes({"2:0": 1.5, "2:1": 3.5}) is None


def test_picks_are_the_likely_ones_most_likely_first():
    picks = likely_picks(_match(), {}, band_of)
    probs = [p["probability"] for p in picks]
    assert probs == sorted(probs, reverse=True) and min(probs) >= 0.5 and len(picks) <= 4
    assert picks[0]["label"] == "Zverev A. gana al menos un set"
    labels = [p["label"] for p in picks]
    assert "Zverev A. gana el partido" in labels and "Zverev A. gana el 1er set" in labels


def test_pick_carries_price_payout_and_history():
    hist = {"Match Winner": {"80-90": {"n": 275, "winRate": 0.884}}}
    p = next(x for x in likely_picks(_match(), hist, band_of) if x["kind"] == "partido")
    assert p["odds"] == 1.2 and p["payPer100"] == 20 and p["oddsKind"] == "directa"
    assert p["band"] == "80-90" and p["history"]["n"] == 275


def test_no_picks_once_started_or_without_prices():
    assert likely_picks(_match(status="FINISHED"), {}, band_of) is None
    assert likely_picks(_match(oddsMarkets={}), {}, band_of) is None


def test_best_of_five_board():
    b = board_outcomes({"3:0": 2.2, "3:1": 3.6, "3:2": 6, "2:3": 13, "1:3": 17, "0:3": 34})
    assert b["bestOf"] == 5
    picks = likely_picks(_match(oddsMarkets={"setBetting": {"3:0": 2.2, "3:1": 3.6, "3:2": 6, "2:3": 13,
                                                            "1:3": 17, "0:3": 34}}), {}, band_of)
    assert any(p["label"] == "Dura 4 sets o más" for p in picks) or picks[0]["kind"] == "unSet"


def test_quoted_at_least_one_set_price_wins_over_the_estimate():
    m = _match()
    m["oddsMarkets"]["oneSet"] = {"p1": {"yes": 1.02, "no": 12.0}}
    p = next(x for x in likely_picks(m, {}, band_of) if x["label"] == "Zverev A. gana al menos un set")
    assert p["odds"] == 1.02 and p["oddsKind"] == "directa" and p["probability"] > 0.9


def test_estimated_price_never_drops_below_one():
    p = next(x for x in likely_picks(_match(), {}, band_of) if x["kind"] == "unSet")
    assert p["oddsKind"] == "aprox" and p["odds"] >= 1.01


def test_history_without_a_real_price_keeps_only_the_hit_rate():
    hist = {"One Set": {"90-100": {"n": 900, "winRate": 0.93, "expected": 0.92, "yield": -0.1}}}
    p = next(x for x in likely_picks(_match(), hist, band_of) if x["kind"] == "unSet")
    assert p["history"] == {"n": 900, "winRate": 0.93, "expected": 0.92}
