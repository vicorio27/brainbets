"""Tests for the tennis ensemble walk-forward check
(`src/application/ensemble_walkforward_service.py`).

No DB access here -- `walk_forward_ensemble` needs it; the scoring and
verdict math are pure functions tested directly against synthetic rows
shaped like `ensemble_weights_service._extract_row`'s output.
"""
import math

import pytest

from src.application import ensemble_walkforward_service as wf


def make_row(label, **features):
    """A training row shaped like `_extract_row`'s output. Unset signals
    default to 0.5 (uninformative) so a test can vary just the ones it cares
    about."""
    full = {k: 0.5 for k in ("surface_elo", "elo", "xgboost", "catboost", "ml", "odds")}
    full.update(features)
    return {"regime": "both", "features": full, "label": label}


EQUAL_WEIGHTS = {k: 1.0 / 6 for k in ("surface_elo", "elo", "xgboost", "catboost", "ml", "odds")}


# ----------------------------------------------------------------------
# _weighted_prob
# ----------------------------------------------------------------------
def test_weighted_prob_is_a_plain_weighted_average():
    features = {"elo": 0.8, "surface_elo": 0.6, "xgboost": None, "catboost": None, "ml": None, "odds": None}
    weights = {"elo": 0.5, "surface_elo": 0.5}

    assert wf._weighted_prob(features, weights) == pytest.approx(0.7)


def test_weighted_prob_skips_missing_signals_and_renormalizes():
    # Only elo has a value; its weight alone should fully determine the result.
    features = {"elo": 0.9, "surface_elo": None, "xgboost": None, "catboost": None, "ml": None, "odds": None}
    weights = {"elo": 0.3, "surface_elo": 0.7}

    assert wf._weighted_prob(features, weights) == pytest.approx(0.9)


def test_weighted_prob_defaults_to_a_toss_up_with_no_usable_signal():
    features = {k: None for k in ("surface_elo", "elo", "xgboost", "catboost", "ml", "odds")}
    assert wf._weighted_prob(features, EQUAL_WEIGHTS) == 0.5


# ----------------------------------------------------------------------
# _score
# ----------------------------------------------------------------------
def test_score_perfect_weights_give_100pct_accuracy_and_low_logloss():
    rows = [make_row(1.0, elo=0.95), make_row(0.0, elo=0.05), make_row(1.0, elo=0.9)]
    weights = {"elo": 1.0}

    result = wf._score(rows, weights)

    assert result["n"] == 3
    assert result["accuracy"] == 100.0
    assert result["logLoss"] < 0.2


def test_score_anti_correlated_weights_give_low_accuracy_and_high_logloss():
    rows = [make_row(1.0, elo=0.1), make_row(0.0, elo=0.9)]
    weights = {"elo": 1.0}

    result = wf._score(rows, weights)

    assert result["accuracy"] == 0.0
    assert result["logLoss"] > 1.5


def test_score_empty_rows_returns_none_not_a_crash():
    assert wf._score([], {"elo": 1.0}) == {"n": 0, "accuracy": None, "logLoss": None}


# ----------------------------------------------------------------------
# _verdict
# ----------------------------------------------------------------------
def test_verdict_generalizes_when_it_beats_baseline_without_a_big_overfit_gap():
    walk_forward = {"accuracy": 70.0, "logLoss": 0.55}
    baseline = {"accuracy": 60.0, "logLoss": 0.65}
    in_sample = {"accuracy": 72.0, "logLoss": 0.52}  # only 2pts better than walk-forward

    assert wf._verdict(walk_forward, baseline, in_sample) == (
        "generaliza: le gana a los pesos fijos en datos que nunca vio, "
        "sin caerse mucho frente al fit con todos los datos"
    )


def test_verdict_flags_overfitting_when_in_sample_is_much_better():
    walk_forward = {"accuracy": 61.0, "logLoss": 0.64}
    baseline = {"accuracy": 60.0, "logLoss": 0.65}
    in_sample = {"accuracy": 80.0, "logLoss": 0.40}  # 19pts better than walk-forward

    verdict = wf._verdict(walk_forward, baseline, in_sample)

    assert "sobreajuste" in verdict


def test_verdict_says_it_does_not_generalize_when_it_loses_to_baseline():
    walk_forward = {"accuracy": 55.0, "logLoss": 0.70}
    baseline = {"accuracy": 60.0, "logLoss": 0.65}
    in_sample = {"accuracy": 58.0, "logLoss": 0.68}

    verdict = wf._verdict(walk_forward, baseline, in_sample)

    assert "no generaliza" in verdict


# ----------------------------------------------------------------------
# walk_forward_ensemble (regime splitting / insufficient-data gating)
# ----------------------------------------------------------------------
def test_walk_forward_ensemble_flags_insufficient_data_for_thin_regimes(monkeypatch):
    # Only 10 "both"-regime rows total -- below MIN_SAMPLES for training alone.
    rows = [make_row(1.0 if i % 2 == 0 else 0.0, elo=0.6) for i in range(10)]
    monkeypatch.setattr(wf, "_load_rows", lambda db: rows)

    result = wf.walk_forward_ensemble(db=None, cutoff_frac=0.7)

    assert result["regimes"]["both"]["status"] == "insufficient_data"
    assert result["regimes"]["elo_only"]["status"] == "insufficient_data"
    assert result["regimes"]["rank_only"]["status"] == "insufficient_data"


def test_walk_forward_ensemble_splits_chronologically_and_scores_each_side(monkeypatch):
    # 60 rows: first 40 are an obvious pattern for the fit to learn (elo
    # alone predicts the label perfectly), last 20 are the same pattern --
    # a fit on the first 40 should generalize cleanly to the last 20.
    rows = [make_row(1.0 if i % 2 == 0 else 0.0, elo=0.9 if i % 2 == 0 else 0.1) for i in range(60)]
    monkeypatch.setattr(wf, "_load_rows", lambda db: rows)

    result = wf.walk_forward_ensemble(db=None, cutoff_frac=0.7)

    both = result["regimes"]["both"]
    assert both["status"] == "ok"
    assert both["trainSamples"] == 42  # 60 * 0.7
    assert both["testSamples"] == 18
    assert both["walkForward"]["accuracy"] == 100.0
