"""Tests for the head-to-head shown on each tennis match."""
from datetime import datetime, timezone

from src.application import h2h_service as h


def _d(y, m, d):
    return datetime(y, m, d, 12, tzinfo=timezone.utc)


def test_the_winner_comes_from_the_score_and_old_archive_rows_from_the_id():
    assert h.meeting_winner("TENNIS-12106806", 0, 2) == "player2"
    assert h.meeting_winner("TENNIS-2023-11-01_00:00:00-Altmaier_D.-Fritz_T.", None, None) == "player1"
    assert h.meeting_winner("TENNIS-12106806", None, None) is None


def test_summary_counts_each_meeting_once_newest_first():
    meetings = [
        {"date": _d(2023, 11, 1), "tournament": "Paris", "p1Won": True, "sets": None},
        {"date": _d(2025, 5, 26), "tournament": "French Open", "p1Won": True, "sets": "3-1"},
        {"date": _d(2025, 5, 27), "tournament": "Roland Garros", "p1Won": True, "sets": "3-1"},  # same match, other source
        {"date": _d(2024, 3, 1), "tournament": "X", "p1Won": None},
    ]
    s = h.summarize(meetings)

    assert (s["p1Wins"], s["p2Wins"], s["total"]) == (2, 0, 2)
    assert [m["tournament"] for m in s["meetings"]] == ["Roland Garros", "Paris"]


def test_no_decided_meeting_means_no_head_to_head():
    assert h.summarize([]) is None
    assert h.summarize([{"date": _d(2024, 1, 1), "p1Won": None}]) is None
