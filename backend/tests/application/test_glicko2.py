"""Tests for the Glicko-2 rating math (`src/application/glicko2.py`).

No DB access — pure functions only. The `_g`/`_e` reference numbers are the
per-opponent intermediate values from Glickman's published Glicko-2 example
(http://www.glicko.net/glicko/glicko2.pdf, "Step 3"): a player rated 1500
(RD 200) against three opponents rated 1400 (RD 30), 1550 (RD 100) and 1700
(RD 300). Those intermediate g()/E() values don't depend on how many
opponents are batched together, so they validate this module's core math
even though `rate_match` here applies one opponent per call (sequential
single-opponent updates) rather than the paper's batched multi-opponent
period.
"""
import math

import pytest

from src.application import glicko2


def _to_scale(rating, rd):
    return (rating - glicko2.DEFAULT_RATING) / glicko2.SCALE, rd / glicko2.SCALE


@pytest.mark.parametrize(
    "opp_rating,opp_rd,expected_g,expected_e",
    [
        (1400, 30, 0.9955, 0.639),
        (1550, 100, 0.9531, 0.432),
        (1700, 300, 0.7242, 0.303),
    ],
)
def test_g_and_e_match_glickman_worked_example(opp_rating, opp_rd, expected_g, expected_e):
    mu, _ = _to_scale(1500, 200)
    mu_j, phi_j = _to_scale(opp_rating, opp_rd)

    assert glicko2._g(phi_j) == pytest.approx(expected_g, abs=1e-3)
    assert glicko2._e(mu, mu_j, phi_j) == pytest.approx(expected_e, abs=1e-3)


def test_expected_score_symmetric():
    a = glicko2.expected_score(1800, 120, 1450, 80)
    b = glicko2.expected_score(1450, 80, 1800, 120)
    assert a + b == pytest.approx(1.0, abs=1e-9)


def test_expected_score_equal_ratings_is_toss_up():
    assert glicko2.expected_score(1600, 90, 1600, 90) == pytest.approx(0.5, abs=1e-9)


def test_high_rd_shrinks_probability_toward_toss_up():
    """A big rating gap should predict a lopsided match only when both
    ratings are reliable — this is the actual mechanism behind "don't fully
    trust a rating right after a big upset / short turnaround / long
    layoff": widen RD, and the same rating gap now predicts a closer match.
    """
    confident = glicko2.expected_score(1800, 50, 1500, 50)
    one_uncertain = glicko2.expected_score(1800, glicko2.RD_MAX, 1500, 50)

    assert confident > 0.5
    assert 0.5 < one_uncertain < confident


def test_inflate_rd_for_inactivity_grows_and_caps():
    rd = 60.0
    grown = glicko2.inflate_rd_for_inactivity(rd, glicko2.DEFAULT_VOLATILITY, idle_periods=5)
    assert grown > rd

    huge = glicko2.inflate_rd_for_inactivity(rd, glicko2.DEFAULT_VOLATILITY, idle_periods=10_000)
    assert huge == pytest.approx(glicko2.RD_MAX, abs=1e-6)

    assert glicko2.inflate_rd_for_inactivity(rd, glicko2.DEFAULT_VOLATILITY, idle_periods=0) == rd


def test_rate_match_reduces_rd_after_a_result():
    """Observing an outcome should never leave a competitor less certain
    about their rating than they were going in (absent any idle inflation)."""
    new_rating, new_rd, new_volatility = glicko2.rate_match(
        rating=1500, rd=200, volatility=0.06,
        opp_rating=1400, opp_rd=30, score=1.0,
    )
    assert new_rd < 200
    assert new_rating > 1500
    assert new_volatility > 0


def test_rate_match_home_bonus_shifts_expectation_not_baseline():
    """`rating_bonus` should only affect the surprise used to compute the
    update, matching the previous plain-Elo home-advantage behaviour, not
    get baked into the player's own persisted rating baseline."""
    no_bonus, _, _ = glicko2.rate_match(
        rating=1500, rd=80, volatility=0.06,
        opp_rating=1500, opp_rd=80, score=1.0,
    )
    with_bonus, _, _ = glicko2.rate_match(
        rating=1500, rd=80, volatility=0.06,
        opp_rating=1500, opp_rd=80, score=1.0, rating_bonus=65,
    )
    # Winning "as the underdog" (bonus made them look stronger than they are,
    # so the win is less surprising) should raise the rating less than
    # winning with no assumed advantage.
    assert with_bonus < no_bonus
