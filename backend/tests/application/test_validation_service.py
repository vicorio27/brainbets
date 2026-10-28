from types import SimpleNamespace as NS

from src.application.validation_service import _validate_tennis


def _match():
    side = lambda s, n: NS(side=s, competitor=NS(name=n))
    return NS(competitors=[side("player1", "Hanfmann Y."), side("player2", "J-L. Struff")], extra_data={})


def _exact(pick, home, away):
    pred = NS(market="Exact Set Score", predicted_outcome=pick)
    return _validate_tennis(pred, _match(), NS(home_score=home, away_score=away))


def test_exact_score_of_an_away_win_reads_from_the_winner_side():
    r = _exact("J-L. Struff 2-0", 0, 2)
    assert r["actual_outcome"] == "J-L. Struff 2-0" and r["success"] is True


def test_exact_score_still_fails_on_the_wrong_score():
    assert _exact("J-L. Struff 2-0", 1, 2)["success"] is False
    assert _exact("Hanfmann Y. 2-0", 2, 0)["success"] is True
