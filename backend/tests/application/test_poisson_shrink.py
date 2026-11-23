from src.application.poisson_service import shrink


def test_few_matches_are_pulled_towards_the_league_average():
    assert round(shrink(0.38, 5), 3) == 0.69          # five home games: half way
    assert round(shrink(0.38, 0), 3) == 1.0           # nothing played: the average


def test_a_full_season_barely_moves():
    assert abs(shrink(1.4, 19) - 1.4) < 0.1
