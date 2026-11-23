from src.application.goals_trend_service import combine, summarize


def test_needs_a_minimum_of_matches():
    assert summarize([(1, 1)] * 4) is None


def test_a_team_that_scores_and_concedes_every_week():
    s = summarize([(2, 2), (1, 3), (3, 1), (2, 1), (1, 2), (2, 2)])
    assert s["over25"] == 1.0 and s["btts"] == 1.0 and s["cleanSheets"] == 0
    assert s["goalsFor"] == 1.83 and s["goalsAgainst"] == 1.83
    assert any("Más de 2.5 goles en 6 de sus últimos 6" in n for n in s["notes"])
    assert any("Marca y recibe en 6" in n for n in s["notes"])


def test_a_tight_team_gets_the_low_notes():
    s = summarize([(1, 0), (0, 0), (1, 0), (0, 1), (1, 0), (0, 0)])
    assert s["over25"] == 0.0 and s["cleanSheets"] == 5
    assert any("solo 0 de sus últimos 6" in n for n in s["notes"])


def test_combine_averages_both_teams():
    a = summarize([(2, 2)] * 5)
    b = summarize([(0, 0)] * 5)
    assert combine(a, b) == {"over25": 0.5, "btts": 0.5, "goals": 2.0}
    assert combine(a, None) is None
