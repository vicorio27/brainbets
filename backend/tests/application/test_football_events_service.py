from src.application.football_events_service import parse_events


def test_goals_minutes_sides_and_own_goals():
    fx = {"teams": {"home": {"id": 1}, "away": {"id": 2}},
          "score": {"halftime": {"home": 1, "away": 0}},
          "events": [
              {"time": {"elapsed": 12, "extra": None}, "team": {"id": 1}, "type": "Goal", "detail": "Normal Goal"},
              {"time": {"elapsed": 45, "extra": 2}, "team": {"id": 2}, "type": "Goal", "detail": "Penalty"},
              {"time": {"elapsed": 60, "extra": None}, "team": {"id": 1}, "type": "Goal", "detail": "Own Goal"},
              {"time": {"elapsed": 70, "extra": None}, "team": {"id": 2}, "type": "Goal", "detail": "Missed Penalty"},
              {"time": {"elapsed": 80, "extra": None}, "team": {"id": 2}, "type": "Card", "detail": "Red Card"},
              {"time": {"elapsed": 81, "extra": None}, "team": {"id": 2}, "type": "Card", "detail": "Yellow Card"},
          ]}
    out = parse_events(fx)
    assert out["goals"] == [{"m": 12, "x": 0, "s": "home", "k": "g"},
                            {"m": 45, "x": 2, "s": "away", "k": "p"},
                            {"m": 60, "x": 0, "s": "home", "k": "o"}]     # the API lists an own goal under the team that benefits
    assert out["reds"] == [{"m": 80, "s": "away"}]
    assert out["halftime"] == {"home": 1, "away": 0}


def test_a_match_without_events_is_empty_not_an_error():
    out = parse_events({"teams": {"home": {"id": 1}, "away": {"id": 2}}, "events": [], "score": {}})
    assert out == {"goals": [], "reds": [], "halftime": None}
