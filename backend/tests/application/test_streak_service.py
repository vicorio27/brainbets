"""Tests for tournament streak tags (`streak_service`)."""
from src.application import streak_service as ss


def test_upset_by_price_first_then_by_ranking():
    assert ss.was_upset(0.35, 10, 200) is True       # price says underdog, ranking ignored
    assert ss.was_upset(0.55, 200, 10) is False
    assert ss.was_upset(None, 120, 40) is True        # no price: 3x worse ranked
    assert ss.was_upset(None, 50, 40) is False
    assert ss.was_upset(None, None, 40) is False


def test_streak_counts_wins_and_flags_the_last_upset():
    s = ss.player_streak([(True, False), (True, True)], rank=30)
    assert s == {"wins": 2, "upsets": 1, "lastUpset": True, "lowRankRun": False}


def test_low_ranked_run_needs_two_wins():
    assert ss.player_streak([(True, False)], rank=150)["lowRankRun"] is False
    assert ss.player_streak([(True, False), (True, False)], rank=150)["lowRankRun"] is True


def test_no_tag_without_a_win():
    assert ss.player_streak([], rank=10) is None
