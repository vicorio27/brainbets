"""Tests for the empirical exact-set-score prior (redesign of the "Exact Set
Score" market, see `src/application/exact_score_prior_service.py`).

No DB access here -- `train_exact_score_prior`/`get_exact_score_priors` need
it; the bucketing and smoothing math are pure functions tested directly.
"""
import pytest

from src.application import exact_score_prior_service as esp


# ----------------------------------------------------------------------
# _best_of
# ----------------------------------------------------------------------
def test_best_of_prefers_the_stored_value():
    assert esp._best_of({"best_of": 5}, "Some ATP 250") == 5
    assert esp._best_of({"best_of": "3"}, "Wimbledon") == 3  # stored value wins even over a Slam name


def test_best_of_falls_back_to_grand_slam_name_detection():
    assert esp._best_of({}, "Wimbledon") == 5
    assert esp._best_of(None, "US Open") == 5
    assert esp._best_of({}, "Roland Garros") == 5


def test_best_of_defaults_to_3_for_non_slams():
    assert esp._best_of({}, "ATP Masters 1000 Miami") == 3
    assert esp._best_of(None, None) == 3
    assert esp._best_of({"best_of": None}, "Indian Wells") == 3


# ----------------------------------------------------------------------
# _rank_bucket_label
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "rank_diff,expected",
    [
        (0, "0-10"),
        (9.9, "0-10"),
        (10, "10-25"),
        (24, "10-25"),
        (25, "25-50"),
        (49, "25-50"),
        (50, "50-100"),
        (99, "50-100"),
        (100, "100+"),
        (10_000, "100+"),
    ],
)
def test_rank_bucket_label_boundaries(rank_diff, expected):
    assert esp._rank_bucket_label(rank_diff) == expected


# ----------------------------------------------------------------------
# _smoothed_distribution
# ----------------------------------------------------------------------
def test_smoothed_distribution_matches_raw_frequency_with_enough_samples():
    # 600 straight-sets, 400 three-setters: smoothing barely moves a large sample.
    dist = esp._smoothed_distribution({0: 600, 1: 400}, best_of=3)

    assert dist["0"] == pytest.approx(0.6, abs=0.01)
    assert dist["1"] == pytest.approx(0.4, abs=0.01)
    assert sum(dist.values()) == pytest.approx(1.0, abs=1e-9)


def test_smoothed_distribution_avoids_a_hard_zero_for_unseen_outcomes():
    # Every observed match in this (tiny, hypothetical) bucket was a sweep.
    dist = esp._smoothed_distribution({0: 10}, best_of=3)

    assert dist["0"] < 1.0
    assert dist["1"] > 0.0


def test_smoothed_distribution_covers_all_three_outcomes_for_best_of_5():
    dist = esp._smoothed_distribution({0: 50, 1: 30, 2: 20}, best_of=5)

    assert set(dist.keys()) == {"0", "1", "2"}
    assert sum(dist.values()) == pytest.approx(1.0, abs=1e-9)
