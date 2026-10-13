"""Tests for ranking bets by price value (`best_bets_service`)."""
import pytest

from src.application import best_bets_service as bb


def test_edge_is_measured_at_the_best_price_against_the_fair_probability():
    reference = {"p1": 2.11, "p2": 1.80}
    books = {"Pncl": {"p1": 2.11, "p2": 1.80}, "bet365": {"p1": 2.20, "p2": 1.66}, "1xBet": {"p1": 2.05, "p2": 1.75}}

    view = bb.price_view(reference, books, "p1")

    fair = (1 / 2.11) / (1 / 2.11 + 1 / 1.80)
    assert view["fairProbability"] == pytest.approx(fair, abs=1e-4)
    assert (view["bestOdds"], view["bestBook"], view["secondBestOdds"]) == (2.20, "bet365", 2.11)
    assert view["edge"] == pytest.approx(fair * 2.20 - 1, abs=1e-4)
    assert view["level"] == "fair" and view["kelly"] > 0


def test_at_the_reference_price_the_edge_is_minus_the_margin():
    view = bb.price_view({"p1": 1.50, "p2": 2.60}, {"Pncl": {"p1": 1.50, "p2": 2.60}}, "p1")

    assert view["edge"] < 0 and view["level"] == "poor" and view["kelly"] == 0.0


def test_a_price_far_above_the_reference_is_flagged_not_celebrated():
    view = bb.price_view({"p1": 2.00, "p2": 1.85}, {"Pncl": {"p1": 2.00, "p2": 1.85}, "Slow": {"p1": 2.40, "p2": 1.60}}, "p1")

    assert view["edge"] > 0.1 and view["level"] == "check"


def test_levels():
    assert bb.level_for(0.03, 0.02) == "good"
    assert bb.level_for(0.01, 0.02) == "fair"
    assert bb.level_for(-0.01, 0.0) == "poor"


def test_no_reference_price_no_view():
    assert bb.price_view({"p1": 1.9}, {}, "p1") is None
