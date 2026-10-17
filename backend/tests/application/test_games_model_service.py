"""Tests for the frozen games model (`games_model_service`)."""
import pytest

from src.application import games_model_service as gm


def test_distribution_sums_to_one_and_respects_the_format():
    for bo, lo, hi in ((3, 12, 39), (5, 18, 65)):
        raw = gm.raw_games_view(0.64, 0.62, bo)
        assert sum(raw["dist"].values()) == pytest.approx(1.0, abs=1e-9)
        assert min(raw["dist"]) >= lo and max(raw["dist"]) <= hi


def test_even_players_go_the_distance_half_the_time_in_best_of_three():
    raw = gm.raw_games_view(0.65, 0.65, 3)
    assert raw["decider"] == pytest.approx(0.5, abs=1e-6)


def test_a_mismatch_means_fewer_games_and_tiebreaks():
    even = gm.games_view(0.65, 0.65, 3)
    mismatch = gm.games_view(0.72, 0.55, 3)
    assert mismatch["expectedGames"] < even["expectedGames"]
    assert mismatch["tiebreak"] < even["tiebreak"]
    assert mismatch["decider"] < even["decider"]


def test_frozen_shift_moves_the_over_probability():
    view = gm.games_view(0.65, 0.65, 3)
    unshifted = sum(p for g, p in view["dist"].items() if g > 22.5)
    assert gm.over_probability(view, 22.5) < unshifted


def test_complete_sets_rejects_retirements():
    assert gm.complete_sets([{"p1": 6, "p2": 4}, {"p1": 7, "p2": 6}]) == (23, 2, 0, True)
    assert gm.complete_sets([{"p1": 6, "p2": 4}, {"p1": 3, "p2": 2}]) is None
    assert gm.complete_sets([{"p1": 6, "p2": 4}]) is None
    assert gm.complete_sets([{"p1": 4, "p2": 6}, {"p1": 6, "p2": 3}, {"p1": 7, "p2": 5}]) == (31, 2, 1, False)
