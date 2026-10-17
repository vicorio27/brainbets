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


@pytest.mark.parametrize("bo", (3, 5))
def test_set_scores_keep_the_match_winner_and_the_corrected_decider(bo):
    s, decider = 0.62, 0.30
    scores = gm.set_scores(s, bo, decider)
    need = 3 if bo == 5 else 2
    assert sum(scores.values()) == pytest.approx(1.0, abs=1e-3)
    p1 = sum(p for k, p in scores.items() if int(k.split("-")[0]) == need)
    assert p1 == pytest.approx(gm.match_prob(s, bo), abs=1e-3)
    straight = sum(p for k, p in scores.items() if "0" in k.split("-"))
    assert straight == pytest.approx(1 - decider, abs=1e-3)


def test_point_probability_reads_every_tennis_market():
    from src.application.services import point_probability

    pm = gm.point_markets(0.68, 0.62, 3)
    assert point_probability("Match Winner", "B", "A", "B", pm) == pytest.approx(1 - pm["matchP1"])
    assert point_probability("Set 1 Winner", "A", "A", "B", pm) == pm["set1P1"]
    assert point_probability("Total Sets", "Over 2.5", "A", "B", pm) == pm["decider"]
    assert point_probability("Exact Set Score", "Zverev A. 2-1", "x", "Zverev A.", pm) == pm["setScores"]["1-2"]
    assert point_probability("Total Aces", "Over 15.5", "A", "B", pm) is None
