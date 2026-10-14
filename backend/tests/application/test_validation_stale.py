"""Tests for closing predictions that can never be settled (`validation_service.stale_reason`)."""
from datetime import datetime, timedelta, timezone

from src.application import validation_service as vs

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def test_a_cancelled_match_voids_its_predictions():
    assert "anulado" in vs.stale_reason("CANCELLED", NOW - timedelta(hours=5), NOW - timedelta(days=1), NOW)


def test_a_match_still_to_play_or_just_played_stays_open():
    before = NOW - timedelta(days=1)
    assert vs.stale_reason("SCHEDULED", NOW + timedelta(hours=3), before, NOW) is None
    assert vs.stale_reason("LIVE", NOW - timedelta(hours=2), before, NOW) is None
    assert vs.stale_reason("SCHEDULED", NOW - timedelta(days=2), NOW - timedelta(days=3), NOW) is None


def test_a_result_that_never_arrived_closes_the_prediction():
    played = NOW - timedelta(days=4)
    assert "nunca" in vs.stale_reason("SCHEDULED", played, played - timedelta(hours=6), NOW)
    assert "nunca" in vs.stale_reason("LIVE", played, played - timedelta(hours=6), NOW)


def test_a_finished_match_is_left_for_validation():
    played = NOW - timedelta(days=40)
    assert vs.stale_reason("FINISHED", played, played - timedelta(hours=6), NOW) is None


def test_a_prediction_made_after_the_start_is_void():
    played = NOW - timedelta(days=40)
    assert "ya había empezado" in vs.stale_reason("FINISHED", played, played + timedelta(hours=2), NOW)
