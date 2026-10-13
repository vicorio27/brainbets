"""Tests for the Set 1 shadow model (`set1_lab_service`). No DB access."""
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest

from src.application import set1_lab_service as lab


def _rows(n, signal, seed=3):
    """Market always says 50%; the truth depends on feature 0 by `signal`."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        x = [float(rng.normal()) for _ in lab.FEATURES]
        p_true = 1 / (1 + np.exp(-signal * x[0]))
        rows.append(
            {
                "date": (date(2026, 1, 1) + timedelta(days=i // 4)).isoformat(),
                "pMarket": 0.5,
                "won": int(rng.random() < p_true),
                "odds1": 1.9,
                "odds2": 1.9,
                "x": x,
            }
        )
    return rows


def test_no_margin_probability_sums_to_one_across_sides():
    a = lab.no_margin_probability(1.5, 2.6)
    b = lab.no_margin_probability(2.6, 1.5)

    assert a + b == pytest.approx(1.0)
    assert lab.no_margin_probability(None, 2.0) is None
    assert lab.no_margin_probability(1.0, 2.0) is None


def test_shrinkage_keeps_a_player_with_no_matches_at_the_tour_average():
    feats = lab.player_features(lab._Totals(), datetime(2026, 10, 1, tzinfo=timezone.utc))

    assert feats["hold"] == pytest.approx(lab.TOUR_PRIOR["hold"])
    assert feats["s1"] == pytest.approx(0.5)
    assert feats["load"] == 0.0


def test_walk_forward_never_predicts_without_enough_history():
    rows = _rows(lab.MIN_TRAIN_ROWS + 8, signal=1.0)

    preds = lab.walk_forward(rows)

    assert all(p is None for p in preds[: lab.MIN_TRAIN_ROWS])
    assert any(p is not None for p in preds)


def test_a_real_signal_beats_the_market_out_of_sample():
    rows = _rows(900, signal=1.2)

    report = lab.score(rows, lab.walk_forward(rows))

    assert report["improvement"] > 0
    assert report["improvementCiLow"] > 0


def test_pure_noise_does_not_look_like_an_edge():
    rows = _rows(900, signal=0.0)

    report = lab.score(rows, lab.walk_forward(rows))

    assert report["improvementCiLow"] <= 0  # cannot claim to beat the market


def test_verdict_waits_for_untouched_matches():
    assert lab.verdict_for({"matches": 40})["level"] == "juntando_muestra"
    enough = {"matches": lab.MIN_POST_FREEZE, "improvementCiLow": 0.004, "improvementCiHigh": 0.03}
    assert lab.verdict_for(enough)["level"] == "demostrado"
    unclear = {"matches": lab.MIN_POST_FREEZE, "improvementCiLow": -0.01, "improvementCiHigh": 0.02}
    assert lab.verdict_for(unclear)["level"] == "no_demostrado"
    worse = {"matches": lab.MIN_POST_FREEZE, "improvementCiLow": -0.05, "improvementCiHigh": -0.01}
    assert lab.verdict_for(worse)["level"] == "descartado"


def test_total_sets_odds_follow_the_format():
    board = {"2": 1.60, "3": 2.40, "4": 3.0, "5": 6.0}

    assert lab._total_sets_odds({"2": 1.60, "3": 2.40}, 3) == (2.40, 1.60)
    over, under = lab._total_sets_odds(board, 5)
    assert under == 2.40 and over == pytest.approx(2.0)  # "4 or 5 sets" combined
    assert lab._total_sets_odds({"3": 2.40}, 3) is None


def test_total_sets_features_do_not_depend_on_who_is_listed_first():
    a = {"hold": 0.85, "brk": 0.20, "fs": 0.75, "aces": 9.0, "load": 2.0, "rest": 1.0}
    b = {"hold": 0.78, "brk": 0.26, "fs": 0.70, "aces": 4.0, "load": 4.0, "rest": 3.0}

    assert lab._total_features(a, b) == lab._total_features(b, a)
    assert len(lab._total_features(a, b)) == len(lab.TOTAL_FEATURES)


def test_every_lab_has_labels_for_its_signals_and_its_own_file():
    files = {spec["file"] for spec in lab.LABS.values()}

    assert len(files) == len(lab.LABS)
    for spec in lab.LABS.values():
        assert set(spec["features"]) <= set(spec["labels"])
    # The Set 1 freeze predates the others and must not move with them.
    assert lab.LABS["set1"]["frozenAt"] == lab.FROZEN_AT
