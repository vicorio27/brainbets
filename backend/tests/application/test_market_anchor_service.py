"""Tests for the market-anchored probability (`market_anchor_service`).

Pure functions only: no DB, no artifact on disk.
"""
import pytest

from src.application import market_anchor_service as ma


def test_market_probability_removes_the_margin_from_a_two_way_price():
    # 1.80 / 2.00 -> implied 55.6% + 50% = 105.6% -> chosen side 52.6%
    p = ma.market_probability({"oddsDecimal": {"player1": 1.80, "player2": 2.00}}, 1.80)

    assert p == pytest.approx((1 / 1.80) / (1 / 1.80 + 1 / 2.00))


def test_market_probability_uses_the_whole_set_betting_board():
    board = {"2:0": 2.5, "2:1": 4.0, "0:2": 5.0, "1:2": 6.0}
    overround = sum(1 / v for v in board.values())

    p = ma.market_probability({"oddsDecimal": {"chosen": 2.5, "key": "2:0"}}, 2.5, {"setBetting": board})

    assert p == pytest.approx((1 / 2.5) / overround)


def test_market_probability_assumes_a_margin_when_only_one_price_is_known():
    p = ma.market_probability({"oddsDecimal": {"chosen": 2.0}}, 2.0)

    assert p == pytest.approx(0.5 / ma.DEFAULT_OVERROUND)


def test_market_probability_needs_a_price():
    assert ma.market_probability({"oddsDecimal": {}}, None) is None


def _rows(n, p_model, p_market, hit_rate):
    wins = round(n * hit_rate)
    return [(p_model, p_market, 1 if i < wins else 0) for i in range(n)]


def test_fit_weight_ignores_a_model_the_market_beats():
    # Model says 70%, market 50%, reality 50%: the model adds nothing.
    fit = ma.fit_weight(_rows(300, 0.70, 0.50, 0.50))

    assert fit["weight"] == 0.0


def test_fit_weight_trusts_a_model_that_is_right_against_the_market():
    fit = ma.fit_weight(_rows(600, 0.70, 0.50, 0.70))

    assert fit["weight"] >= 0.8
    assert fit["logLossBlend"] < fit["logLossMarket"]


def test_fit_weight_needs_enough_bets():
    assert ma.fit_weight(_rows(ma.MIN_SAMPLES - 1, 0.6, 0.5, 0.6)) is None


def test_anchored_edge_is_minus_the_margin_when_the_model_has_no_weight(monkeypatch):
    monkeypatch.setattr(ma, "model_weight", lambda sport, market: 0.0)
    monkeypatch.setattr(ma, "model_probability", lambda sport, market, confidence: 0.75)

    out = ma.anchored_probability(
        "tennis", "Match Winner", 75, {"oddsDecimal": {"player1": 1.80, "player2": 2.00}}, 2.00
    )

    assert out["edge"] < 0
    assert out["edge"] == pytest.approx(1 / (1 / 1.80 + 1 / 2.00) - 1)


def test_anchored_probability_sits_between_model_and_market(monkeypatch):
    monkeypatch.setattr(ma, "model_weight", lambda sport, market: 0.25)
    monkeypatch.setattr(ma, "model_probability", lambda sport, market, confidence: 0.70)

    out = ma.anchored_probability(
        "tennis", "Match Winner", 70, {"oddsDecimal": {"player1": 2.0, "player2": 2.0}}, 2.0
    )

    assert out["marketProbability"] == pytest.approx(0.5)
    assert out["probability"] == pytest.approx(0.55)
    assert out["edge"] == pytest.approx(0.10)
