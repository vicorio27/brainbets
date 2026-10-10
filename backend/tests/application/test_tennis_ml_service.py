"""Tests for the side-symmetry of the tennis ML model (`tennis_ml_service`)."""
import numpy as np
import pytest

from src.application import tennis_ml_service as ml


def test_mirror_swaps_players_and_flips_differences():
    vector = [120.0, 80.0, -15.0, 0.7, 0.4, 0.8, 0.3, 2.0, 9.0, 6.0, 1.0]

    mirrored = ml.mirror_features(vector, ml.FEATURE_NAMES)

    assert mirrored == [-120.0, -80.0, 15.0, 0.4, 0.7, 0.3, 0.8, 9.0, 2.0, 1.0, 6.0]
    assert ml.mirror_features(mirrored, ml.FEATURE_NAMES) == vector


def test_mirror_works_on_the_legacy_seven_feature_models():
    names = ml.FEATURE_NAMES[:7]

    assert ml.mirror_features([10.0, 5.0, 3.0, 0.6, 0.5, 0.7, 0.2], names) == [-10.0, -5.0, -3.0, 0.5, 0.6, 0.2, 0.7]


class _BiasedModel:
    """Always favours whoever is listed first, like the pre-fix model did."""

    def predict_proba(self, x):
        p = np.full(len(x), 0.9)
        return np.column_stack([1 - p, p])


class _Identity:
    def transform(self, x):
        return x


def test_symmetric_inference_cancels_a_listing_order_bias():
    artifact = {"model": _BiasedModel(), "scaler": _Identity(), "feature_names": ml.FEATURE_NAMES, "symmetric": True}

    out = ml._predict_rows(artifact, [[0.0] * len(ml.FEATURE_NAMES)])

    assert out[0]["player1"] == pytest.approx(0.5)
    assert out[0]["player1"] + out[0]["player2"] == pytest.approx(1.0)


def test_old_artifacts_are_served_unchanged():
    artifact = {"model": _BiasedModel(), "scaler": _Identity(), "feature_names": ml.FEATURE_NAMES}

    assert ml._predict_rows(artifact, [[0.0] * len(ml.FEATURE_NAMES)])[0]["player1"] == pytest.approx(0.9)
