from datetime import datetime, timezone

from src.application.first_game_service import first_game, first_game_item, same_player


def ev(served, won, set_no="Set 1", game="1"):
    return {"pointbypoint": [{"set_number": set_no, "number_game": game,
                              "player_served": served, "serve_winner": won}]}


def test_first_game_reads_server_and_winner_of_game_one_of_set_one():
    assert first_game(ev("First Player", "First Player")) == (1, 1)
    assert first_game(ev("Second Player", "First Player")) == (2, 1)
    assert first_game({"pointbypoint": [{"set_number": "Set 2", "number_game": "1",
                                         "player_served": "First Player", "serve_winner": "First Player"}]}) is None
    assert first_game({}) is None


def test_same_player_handles_feed_abbreviations_and_the_zverev_brothers():
    assert same_player("C. Alcaraz", "Carlos Alcaraz")
    assert same_player("C. Alcaraz", "Alcaraz C.")
    assert same_player("T. M. Etcheverry", "Tomas Martin Etcheverry")
    assert same_player("A. Zverev", "Alexander Zverev")
    assert not same_player("A. Zverev", "Zverev M.")
    assert not same_player("A. Zverev", "Mischa Zverev")


def _rows(held, lost, returned_won, returned_lost):
    d = datetime(2026, 1, 1, tzinfo=timezone.utc)
    mk = lambda s, w: {"served": s, "won": w, "date": d, "rival": "X", "tournament": "T"}
    return ([mk(True, True)] * held + [mk(True, False)] * lost
            + [mk(False, True)] * returned_won + [mk(False, False)] * returned_lost)


def test_first_game_item_counts_holds_and_needs_enough_games():
    assert first_game_item(_rows(5, 0, 3, 3)) is None
    it = first_game_item(_rows(36, 4, 29, 56))
    assert it["short"] == "36/40 (90%)"
    assert "defendió 36 de 40" in it["text"] and "ganó 29 de 85 (34%)" in it["text"]
    assert first_game_item(_rows(10, 0, 0, 0))["detail"].startswith("Perdió su primer game al sacar primero: nunca")


def test_h2h_first_game_counts_who_served_and_held_between_the_two():
    from src.application.first_game_service import h2h_first_game
    assert h2h_first_game([]) is None
    got = h2h_first_game([
        {"server_p1": True, "winner_p1": True},     # p1 served and held
        {"server_p1": False, "winner_p1": True},    # p2 served and lost it
        {"server_p1": False, "winner_p1": False},   # p2 served and held
    ])
    assert got == {"n": 3, "p1": {"served": 1, "held": 1}, "p2": {"served": 2, "held": 1}}
