"""Tests for Closing Line Value (CLV) math (`src/application/clv_service.py`).

No DB/HTTP access here -- `capture_closing_odds` needs both; the parsing and
CLV math are pure functions tested directly, mirroring the raw api-tennis
get_odds shape so these tests also guard the port from the n8n JS helpers.
"""
import pytest

from src.application import clv_service as clv


# ----------------------------------------------------------------------
# extract_odds_markets / _pick_odd
# ----------------------------------------------------------------------
def test_extracts_all_four_market_shapes_from_a_raw_odds_payload():
    raw = {
        "Home/Away": {"Home": {"bet365": "1.80"}, "Away": {"bet365": "2.10"}},
        "Home/Away (1st Set)": {"Home": {"bet365": "1.70"}, "Away": {"bet365": "2.20"}},
        "Number of sets": {"2": {"bet365": "1.90"}, "3": {"bet365": "1.95"}},
        "Set Betting": {"2:0": {"bet365": "2.50"}, "2:1": {"bet365": "3.40"}},
    }

    parsed = clv.extract_odds_markets(raw)

    assert parsed["matchWinner"] == {"p1": 1.80, "p2": 2.10}
    assert parsed["set1Winner"] == {"p1": 1.70, "p2": 2.20}
    assert parsed["numberOfSets"] == {"2": 1.90, "3": 1.95}
    assert parsed["setBetting"] == {"2:0": 2.50, "2:1": 3.40}


def test_pick_odd_prefers_the_bookmaker_priority_order():
    # bet365 outranks a bookmaker not in BOOKIE_PRIORITY at all.
    selection = {"SomeOtherBook": "5.00", "bet365": "1.80"}
    assert clv._pick_odd(selection) == 1.80


def test_pick_odd_falls_back_to_any_available_price():
    selection = {"ObscureBook": "2.05"}
    assert clv._pick_odd(selection) == 2.05


def test_pick_odd_ignores_degenerate_or_missing_prices():
    assert clv._pick_odd({"bet365": "1.0"}) is None  # not > 1.0
    assert clv._pick_odd({"bet365": "not-a-number"}) is None
    assert clv._pick_odd(None) is None
    assert clv._pick_odd({}) is None


def test_extract_odds_markets_omits_empty_markets_and_handles_missing_data():
    raw = {"Home/Away": {"Home": {"bet365": "1.80"}}}  # no Away price -> incomplete
    assert clv.extract_odds_markets(raw) is None
    assert clv.extract_odds_markets(None) is None
    assert clv.extract_odds_markets({}) is None


# ----------------------------------------------------------------------
# closing_odds_for_prediction
# ----------------------------------------------------------------------
CLOSING = {
    "matchWinner": {"p1": 1.75, "p2": 2.05},
    "set1Winner": {"p1": 1.65, "p2": 2.25},
    "numberOfSets": {"2": 1.85, "3": 1.95, "4": 3.50, "5": 4.20},
    "setBetting": {"2:0": 2.40, "2:1": 3.30, "0:2": 2.60, "1:2": 3.10},
}


def test_closing_odds_for_match_winner_picks_the_predicted_players_side():
    home = clv.closing_odds_for_prediction(
        CLOSING, "Match Winner", "Alcaraz", "Alcaraz", "Sinner", {}
    )
    away = clv.closing_odds_for_prediction(
        CLOSING, "Match Winner", "Sinner", "Alcaraz", "Sinner", {}
    )
    assert home == 1.75
    assert away == 2.05


def test_closing_odds_for_set1_winner_uses_the_set1_market():
    assert clv.closing_odds_for_prediction(
        CLOSING, "Set 1 Winner", "Alcaraz", "Alcaraz", "Sinner", {}
    ) == 1.65


def test_closing_odds_for_total_sets_best_of_3_uses_the_2_3_split():
    over = clv.closing_odds_for_prediction(
        CLOSING, "Total Sets", "Over 2.5", "Alcaraz", "Sinner", {"bestOf": 3}
    )
    under = clv.closing_odds_for_prediction(
        CLOSING, "Total Sets", "Under 2.5", "Alcaraz", "Sinner", {"bestOf": 3}
    )
    assert over == 1.95   # "3" sets
    assert under == 1.85  # "2" sets


def test_closing_odds_for_total_sets_best_of_5_combines_4_and_5():
    over = clv.closing_odds_for_prediction(
        CLOSING, "Total Sets", "Over 3.5", "Alcaraz", "Sinner", {"bestOf": 5}
    )
    under = clv.closing_odds_for_prediction(
        CLOSING, "Total Sets", "Under 3.5", "Alcaraz", "Sinner", {"bestOf": 5}
    )
    # fair combined odd for "4 or 5 sets": 1 / (1/3.50 + 1/4.20)
    assert over == pytest.approx(1 / (1 / 3.50 + 1 / 4.20), abs=1e-3)
    assert under == 1.95  # under 3.5 means exactly 3 sets -> the "3" price


def test_closing_odds_for_exact_set_score_uses_the_stored_key():
    reasoning_data = {"oddsDecimal": {"key": "2:1"}}
    assert clv.closing_odds_for_prediction(
        CLOSING, "Exact Set Score", "Alcaraz 2-1", "Alcaraz", "Sinner", reasoning_data
    ) == 3.30


def test_closing_odds_for_exact_set_score_without_a_stored_key_is_none():
    assert clv.closing_odds_for_prediction(
        CLOSING, "Exact Set Score", "Alcaraz 2-1", "Alcaraz", "Sinner", {}
    ) is None


def test_closing_odds_returns_none_without_a_snapshot_or_unknown_market():
    assert clv.closing_odds_for_prediction(None, "Match Winner", "Alcaraz", "Alcaraz", "Sinner", {}) is None
    assert clv.closing_odds_for_prediction(CLOSING, "Total Aces", "Over 15.5", "Alcaraz", "Sinner", {}) is None
    assert clv.closing_odds_for_prediction(CLOSING, "Match Winner", None, "Alcaraz", "Sinner", {}) is None


# ----------------------------------------------------------------------
# compute_clv
# ----------------------------------------------------------------------
def test_compute_clv_positive_when_our_odds_beat_the_closing_line():
    # We got 2.00, the market closed at 1.80 -> we got a better (higher) price.
    assert clv.compute_clv(2.00, 1.80) == pytest.approx(0.1111, abs=1e-3)


def test_compute_clv_negative_when_the_line_moved_against_us():
    assert clv.compute_clv(1.80, 2.00) == pytest.approx(-0.10, abs=1e-3)


def test_compute_clv_zero_when_odds_matched_the_close():
    assert clv.compute_clv(1.80, 1.80) == 0.0


def test_compute_clv_none_without_both_prices():
    assert clv.compute_clv(None, 1.80) is None
    assert clv.compute_clv(1.80, None) is None
    assert clv.compute_clv(1.80, 1.0) is None  # degenerate closing price
