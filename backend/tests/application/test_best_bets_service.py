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


def test_band_of_puts_favourites_in_ten_point_bands():
    assert bb.band_of(0.55) == "50-60"
    assert bb.band_of(0.70) == "70-80"
    assert bb.band_of(0.97) == "90-100"
    assert bb.band_of(0.45) is None


def test_band_summary_reports_hit_rate_against_fair_and_flat_yield():
    # 4 bets at 1.25 (fair 0.75): 3 wins -> +0.25*3 - 1 = -0.25 over 4 = -6.25%
    s = bb.band_summary([(True, 1.25, 0.75)] * 3 + [(False, 1.25, 0.75)])
    assert s["n"] == 4
    assert s["winRate"] == 0.75
    assert s["expected"] == 0.75
    assert s["yield"] == pytest.approx(-0.0625)
    assert s["yieldLow"] < s["yield"] < s["yieldHigh"]


def test_first_set_winner_from_stored_sets():
    assert bb._first_set_p1([{"p1": 6, "p2": 4}]) is True
    assert bb._first_set_p1([[3, 6], [6, 1]]) is False
    assert bb._first_set_p1([]) is None
