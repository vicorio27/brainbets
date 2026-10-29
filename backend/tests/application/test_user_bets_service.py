from src.application.user_bets_service import bet_outcome, profit_of, settle_leg, summarize, valid_selector

P1, P2 = {"side": "p1"}, {"side": "p2"}


def test_match_and_set_markets_from_the_final_score():
    # Hanfmann (p1) - Struff (p2), 0-2
    assert settle_leg("partido", P2, "FINISHED", 0, 2, False) == "WON"
    assert settle_leg("partido", P1, "FINISHED", 0, 2, False) == "LOST"
    assert settle_leg("sinCeder", P2, "FINISHED", 0, 2, False) == "WON"
    assert settle_leg("sinCeder", P2, "FINISHED", 1, 2, False) == "LOST"
    assert settle_leg("unSet", P1, "FINISHED", 1, 2, True) == "WON"
    assert settle_leg("unSet", P1, "FINISHED", 0, 2, False) == "LOST"
    assert settle_leg("sets", {"sets": "corridos"}, "FINISHED", 0, 2, None) == "WON"
    assert settle_leg("sets", {"sets": "largo"}, "FINISHED", 2, 1, None) == "WON"


def test_first_set_from_the_set_rows_or_a_straight_sets_win():
    assert settle_leg("set1", P1, "FINISHED", 1, 2, True) == "WON"
    assert settle_leg("set1", P1, "FINISHED", 0, 2, None) == "LOST"   # straight sets: winner took set 1
    assert settle_leg("set1", P1, "FINISHED", 2, 1, None) is None    # three sets, no set rows: wait


def test_unfinished_waits_and_cancelled_voids():
    assert settle_leg("partido", P1, "SCHEDULED", None, None, None) is None
    assert settle_leg("partido", P1, "LIVE", 1, 0, True) is None
    assert settle_leg("partido", P1, "CANCELLED", None, None, None) == "VOID"


def test_combo_lost_on_one_leg_and_void_legs_price_one():
    assert bet_outcome([("WON", 1.2), ("LOST", 1.1)]) == ("LOST", 0.0)
    assert bet_outcome([("WON", 1.2), ("PENDING", 1.1)]) == ("PENDING", None)
    assert bet_outcome([("LOST", 1.2), ("PENDING", 1.1)]) == ("LOST", 0.0)   # lost before the rest finishes
    assert bet_outcome([("WON", 1.2), ("VOID", 1.1)]) == ("WON", 1.2)
    assert bet_outcome([("VOID", 1.2)]) == ("VOID", 1.0)
    assert bet_outcome([("WON", 1.16), ("WON", 1.08)]) == ("WON", 1.253)


def test_profit_and_summary():
    assert profit_of("WON", 1_000_000, 1.253) == 253_000.0
    assert profit_of("LOST", 1_000_000, 0.0) == -1_000_000
    bets = [
        {"status": "WON", "amount": 100.0, "profit": 25.0, "probability": 0.72},
        {"status": "LOST", "amount": 100.0, "profit": -100.0, "probability": 0.72},
        {"status": "PENDING", "amount": 50.0, "profit": None, "probability": 0.8},
    ]
    s = summarize(bets)
    assert s["won"] == 1 and s["lost"] == 1 and s["pending"] == 1 and s["staked"] == 200
    assert s["profit"] == -75 and s["yield"] == -0.375 and s["winRate"] == 0.5 and s["expectedWinRate"] == 0.72
    assert s["pendingStaked"] == 50


def test_selector_validation():
    assert valid_selector("partido", P1) and valid_selector("sets", {"sets": "largo"})
    assert not valid_selector("sets", P1) and not valid_selector("aces", P1) and not valid_selector("set1", {"side": "x"})
