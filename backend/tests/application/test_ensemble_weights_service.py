"""Tests for the tennis ensemble weight fitting
(`src/application/ensemble_weights_service.py`).

No DB access here -- `train_ensemble_weights` needs it; `_regime`,
`_extract_row` and `_fit_regime` are pure functions tested directly.
"""
import pytest

from src.application import ensemble_weights_service as ews


# ----------------------------------------------------------------------
# _regime
# ----------------------------------------------------------------------
def test_regime_both_when_elo_and_surface_elo_are_real():
    assert ews._regime({"eloSource": "real", "surfaceEloSource": "real"}) == "both"


def test_regime_elo_only_when_surface_elo_is_estimated():
    assert ews._regime({"eloSource": "real", "surfaceEloSource": "estimado por superficie/aces"}) == "elo_only"


def test_regime_rank_only_when_neither_is_real():
    assert ews._regime({"eloSource": "estimado", "surfaceEloSource": "estimado"}) == "rank_only"
    assert ews._regime({}) == "rank_only"


# ----------------------------------------------------------------------
# _extract_row
# ----------------------------------------------------------------------
def _reasoning_data(**overrides):
    base = {
        "model": "ensemble",
        "elo": {"player1": 0.6, "player2": 0.4},
        "surface_elo": {"player1": 0.65, "player2": 0.35},
        "xgboost": {"player1": 0.55, "player2": 0.45},
        "catboost": {"player1": 0.58, "player2": 0.42},
        "ml": {"player1": 0.62, "player2": 0.38},
        "odds": {"player1": 0.6, "player2": 0.4},
        "eloSource": "real",
        "surfaceEloSource": "real",
    }
    base.update(overrides)
    return base


def test_extract_row_validated_means_the_predicted_side_won():
    row = ews._extract_row(_reasoning_data(), {"player1": 0.6, "player2": 0.4}, "VALIDATED")

    assert row["label"] == 1.0  # player1 was predicted and validated as the winner
    assert row["regime"] == "both"
    assert row["features"]["elo"] == 0.6


def test_extract_row_failed_flips_the_label_to_the_other_side():
    row = ews._extract_row(_reasoning_data(), {"player1": 0.6, "player2": 0.4}, "FAILED")

    assert row["label"] == 0.0  # player1 was predicted but player2 actually won


def test_extract_row_none_for_non_ensemble_or_unvalidated_predictions():
    assert ews._extract_row(_reasoning_data(model="binomial_sets"), {"player1": 0.6, "player2": 0.4}, "VALIDATED") is None
    assert ews._extract_row(_reasoning_data(), {"player1": 0.6, "player2": 0.4}, "PENDING") is None
    assert ews._extract_row(None, {"player1": 0.6, "player2": 0.4}, "VALIDATED") is None


def test_extract_row_none_when_a_required_signal_is_missing():
    # elo missing entirely -- can't form a complete training row.
    rd = _reasoning_data()
    del rd["elo"]
    assert ews._extract_row(rd, {"player1": 0.6, "player2": 0.4}, "VALIDATED") is None


# ----------------------------------------------------------------------
# _fit_regime
# ----------------------------------------------------------------------
def _row(label, **features):
    full = {k: 0.5 for k in ews.MODEL_KEYS}
    full.update(features)
    return {"regime": "both", "features": full, "label": label}


def test_fit_regime_returns_insufficient_below_min_samples():
    rows = [_row(1.0, elo=0.9) for _ in range(ews.MIN_SAMPLES - 5)]

    weights, n, source = ews._fit_regime(rows, ews.DEFAULT_WEIGHTS["both"])

    assert source == "insufficient_samples"
    assert weights == {}
    assert n == len(rows)


def test_fit_regime_weights_sum_to_one_and_stay_in_model_keys():
    rows = [_row(1.0 if i % 2 == 0 else 0.0, elo=0.9 if i % 2 == 0 else 0.1) for i in range(60)]

    weights, n, source = ews._fit_regime(rows, ews.DEFAULT_WEIGHTS["both"])

    assert source == "fitted"
    assert n == 60
    assert set(weights.keys()) == set(ews.MODEL_KEYS)
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)
    assert all(w >= 0 for w in weights.values())


def test_fit_regime_shrinks_toward_defaults_with_few_real_samples():
    """At MIN_SAMPLES (the smallest fittable sample), PRIOR_STRENGTH pseudo-
    samples should still dominate enough that the fit stays close to the
    defaults -- the whole point of the ridge shrinkage."""
    defaults = ews.DEFAULT_WEIGHTS["both"]
    # A real pattern that, unshrunk, would push weight entirely onto "elo".
    rows = [_row(1.0 if i % 2 == 0 else 0.0, elo=0.95 if i % 2 == 0 else 0.05) for i in range(ews.MIN_SAMPLES)]

    weights, _, source = ews._fit_regime(rows, defaults)

    assert source == "fitted"
    # Every other signal keeps a non-trivial share of the defaults' weight --
    # it wasn't zeroed out despite carrying no information in this sample.
    for key in ews.MODEL_KEYS:
        if key == "elo":
            continue
        assert weights[key] > defaults[key] * 0.3
