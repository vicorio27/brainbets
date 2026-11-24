from src.application import tennis_simulation_service as ts


def test_per_set_probabilities_make_sense():
    sets = ts.per_set(0.66, 0.66, 3)
    assert len(sets) == 3
    assert sets[0]["played"] == 1.0 and sets[1]["played"] > 0.99
    assert 0.2 < sets[2]["played"] < 0.6            # a third set is played in a fair share of even matches
    assert abs(sets[0]["p1Wins"] - 0.5) < 0.01       # symmetric players: a coin flip
    assert 8 < sets[0]["games"] < 11 and 0 < sets[0]["tiebreak"] < 0.3


def test_the_stronger_server_wins_more_sets_and_best_of_five_has_five():
    sets = ts.per_set(0.72, 0.62, 5)
    assert len(sets) == 5 and sets[0]["p1Wins"] > 0.7
    assert sets[4]["played"] < sets[2]["played"]


def test_games_shift_moves_the_match_total_by_exactly_the_shift():
    raw = ts.per_set(0.66, 0.64, 3)
    shifted = ts.apply_games_shift(raw, -2.0)
    total = lambda rows: sum(r["played"] * r["games"] for r in rows)
    assert abs((total(shifted) - total(raw)) + 2.0) < 0.05


def test_holds_and_breaks_favour_the_better_server():
    hb = ts.holds_and_breaks(0.70, 0.60, 22.0)
    assert hb["p1"]["hold"] > hb["p2"]["hold"]
    assert hb["p1"]["breaksExpected"] > hb["p2"]["breaksExpected"]   # the weaker server is broken more
