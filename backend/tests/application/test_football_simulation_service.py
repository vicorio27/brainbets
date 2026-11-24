from src.application import football_simulation_service as sim


def test_minutes_fall_in_the_right_band():
    assert [sim.band_of(m) for m in (1, 15, 16, 45, 46, 90, 94)] == [0, 0, 1, 2, 3, 5, 5]


def test_band_counts_only_the_scoring_side():
    goals = [{"m": 10, "s": "home"}, {"m": 44, "s": "away"}, {"m": 80, "s": "home"}]
    assert sim.band_counts(goals, "home") == [1, 0, 0, 0, 0, 1]
    assert sim.band_counts(goals, "away") == [0, 0, 1, 0, 0, 0]


def test_shares_shrink_to_the_league_shape_and_sum_to_one():
    shape = [1 / 6] * 6
    assert abs(sum(sim.shares([0] * 6, shape)) - 1) < 1e-9
    assert all(abs(x - 1 / 6) < 1e-9 for x in sim.shares([0] * 6, shape))                     # no data: the league shape
    heavy = sim.shares([0, 0, 0, 0, 0, 100], shape)                       # lots of late goals pull the share up
    assert heavy[5] > 0.7 and abs(sum(heavy) - 1) < 1e-9


def test_minute_view_splits_the_expected_goals():
    flat = [1 / 6] * 6
    bands = sim.minute_view(1.5, 1.0, flat, flat, flat, flat)
    assert len(bands) == 6
    assert abs(sum(b["home"] for b in bands) - 1.5) < 0.01 and abs(sum(b["away"] for b in bands) - 1.0) < 0.01


def test_goal_markets_are_consistent():
    g = sim.goal_markets(1.6, 1.1)
    assert abs(g["home"] + g["draw"] + g["away"] - 1) < 1e-3
    assert g["over"]["0.5"] > g["over"]["1.5"] > g["over"]["2.5"] > g["over"]["3.5"]
    assert g["home"] > g["away"] and len(g["scorelines"]) == 5
