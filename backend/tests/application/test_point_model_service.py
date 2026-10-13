"""Tests for the serve/return point model (`point_model_service`)."""
from datetime import datetime, timedelta, timezone

import pytest

from src.application import point_model_service as pm


def test_even_points_give_even_games_sets_and_matches():
    assert pm.game_prob(0.5) == pytest.approx(0.5)
    assert pm.tiebreak_prob(0.6, 0.6) == pytest.approx(0.5)
    assert pm.set_prob(0.64, 0.64) == pytest.approx(0.5)
    assert pm.match_prob(0.5, 3) == pytest.approx(0.5)
    assert pm.match_prob(0.5, 5) == pytest.approx(0.5)


def test_known_game_value():
    # A server winning 60% of points holds 73.6% of the time.
    assert pm.game_prob(0.6) == pytest.approx(0.7357, abs=1e-4)


def test_a_small_point_edge_grows_through_the_scoring_system():
    s = pm.set_prob(0.66, 0.62)

    assert 0.5 < s < pm.match_prob(s, 3) < pm.match_prob(s, 5)
    assert pm.set_prob(0.62, 0.66) == pytest.approx(1.0 - s)


def test_deciding_sets_are_likeliest_between_equals():
    assert pm.deciding_sets_prob(0.5, 3) == pytest.approx(0.5)
    assert pm.deciding_sets_prob(0.5, 5) == pytest.approx(0.75)
    assert pm.deciding_sets_prob(0.8, 3) < pm.deciding_sets_prob(0.5, 3)


def test_rates_start_at_the_tour_average_and_favour_recent_same_surface_matches():
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    log = pm.PlayerLog()

    assert log.rates(now, "hard", 0.64) == (pytest.approx(0.64), pytest.approx(0.36), 0.0)

    log.add(now - timedelta(days=10), "hard", 70, 100, 40, 100)     # recent, same surface
    log.add(now - timedelta(days=900), "clay", 50, 100, 20, 100)   # old, other surface
    serve, ret, points = log.rates(now, "hard", 0.64)

    assert 0.64 < serve < 0.70 and 0.36 < ret < 0.40   # pulled by the recent match, shrunk to the tour
    assert 97 < points < 102                            # the old clay match barely counts


def test_serve_probability_is_measured_against_the_opponents_return():
    strong_server, weak_returner, strong_returner = (0.70, 0.36, 500), (0.64, 0.30, 500), (0.64, 0.42, 500)

    vs_weak, _ = pm.serve_point_probs(strong_server, weak_returner, 0.64)
    vs_strong, _ = pm.serve_point_probs(strong_server, strong_returner, 0.64)

    assert vs_weak == pytest.approx(0.76) and vs_strong == pytest.approx(0.64)
