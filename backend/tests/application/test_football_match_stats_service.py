from datetime import datetime

from src.application import football_match_stats_service as s


def _side(tid, **stats):
    return {"team": {"id": tid}, "statistics": [{"type": k, "value": v} for k, v in stats.items()]}


def test_number_strips_percent_and_rejects_text():
    assert s.number("55%") == 55.0
    assert s.number(7) == 7.0
    assert s.number(None) is None
    assert s.number("n/a") is None


def test_parse_stats_assigns_sides_by_team_id_not_by_order():
    resp = [_side(2, **{"Corner Kicks": 3, "Ball Possession": "40%"}), _side(1, **{"Corner Kicks": 8})]
    out = s.parse_stats(resp, home_id=1, away_id=2)
    assert out["home"]["corner_kicks"] == 8.0
    assert out["away"] == {"corner_kicks": 3.0, "ball_possession": 40.0}


def test_parse_stats_falls_back_to_order_and_returns_none_when_empty():
    out = s.parse_stats([_side(9, Fouls=5), _side(8, Fouls=6)], None, None)
    assert out["home"]["fouls"] == 5.0
    assert s.parse_stats([], 1, 2) is None
    assert s.parse_stats([_side(1), _side(2)], 1, 2) is None


def test_find_fixture_tolerates_one_day_of_difference():
    idx = {("2025-03-02", "Man City", "Arsenal"): {"id": 7, "home_id": 1, "away_id": 2}}
    assert s.find_fixture(idx, datetime(2025, 3, 1), "Man City", "Arsenal")["id"] == 7
    assert s.find_fixture(idx, datetime(2025, 3, 5), "Man City", "Arsenal") is None
