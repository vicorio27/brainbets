from datetime import datetime, timezone

from src.application.context_service import (
    group_stakes, indoor_item, is_indoor, news_items, stakes_item, top10_item,
)


def d(y, m, day):
    return datetime(y, m, day, tzinfo=timezone.utc)


# --- indoor ---

def test_indoor_uses_the_stored_court_first():
    assert is_indoor("Miami", d(2019, 3, 20), "Indoor") is True
    assert is_indoor("Finals - Turin", d(2026, 11, 15), "Outdoor") is False


def test_indoor_by_tournament_name_and_season():
    assert is_indoor("Finals - Turin", d(2026, 11, 15)) is True
    assert is_indoor("Swiss Indoors", d(2026, 10, 25)) is True
    assert is_indoor("BNP Paribas Masters", d(2026, 10, 30)) is True
    assert is_indoor("Paris", d(2026, 11, 1)) is True
    assert is_indoor("Lyon", d(2026, 5, 20)) is False      # clay in May
    assert is_indoor("Lyon", d(2026, 10, 20)) is True      # indoor hard in October
    assert is_indoor("Miami", d(2026, 3, 20)) is False
    assert is_indoor("ATP Davis Cup - World Group", d(2026, 9, 12)) is None


def test_indoor_item_flags_a_clear_gap_only_with_enough_matches():
    assert indoor_item([(True, True)] * 5) is None
    rows = [(True, True)] * 8 + [(True, False)] * 2 + [(False, True)] * 6 + [(False, False)] * 4
    it = indoor_item(rows)
    assert it["tone"] == "good" and "80% (8-2)" in it["text"] and "60%" in it["text"]
    worse = [(True, True)] * 5 + [(True, False)] * 5 + [(False, True)] * 8 + [(False, False)] * 2
    assert indoor_item(worse)["tone"] == "bad"


# --- top 10 ---

def test_top10_without_a_win_this_year_is_flagged():
    rows = [{"date": d(2026, m, 1), "won": False, "rank": 5, "rival": "X"} for m in (2, 5, 8)]
    it = top10_item(rows, 2026, opp_rank=7)
    assert it["tone"] == "bad"
    assert "0-3 (ninguna victoria)" in it["text"] and "otra oportunidad" in it["text"]


def test_top10_names_the_last_win():
    rows = [{"date": d(2026, 3, 1), "won": True, "rank": 3, "rival": "A"},
            {"date": d(2026, 9, 1), "won": True, "rank": 8, "rival": "B"},
            {"date": d(2026, 10, 1), "won": False, "rank": 2, "rival": "C"}]
    it = top10_item(rows, 2026, opp_rank=40)
    assert it["tone"] == "good" and "2-1" in it["text"]
    assert "B (#8) el 2026-09-01" in it["detail"]


def test_top10_says_nothing_without_top10_matches_or_rival():
    assert top10_item([], 2026, opp_rank=30) is None


# --- Finals group stakes ---

def test_group_shelton_before_his_third_match():
    # 19-nov: Zverev beat Jodar and Shelton, Shelton beat Fils, Fils beat Jodar; Zverev-Fils still to play
    results = [("Zverev", "Jodar"), ("Shelton", "Fils"), ("Fils", "Jodar"), ("Zverev", "Shelton")]
    st = group_stakes(results, [("Zverev", "Fils")], "Shelton", "Jodar")
    assert st["win"] == {"in", "tie"}          # through, or a three-way tie at 2-1
    assert st["lose"] == {"tie", "out"}        # out unless a three-way tie at 1-2
    it = stakes_item((1, 1), st)
    assert it["tone"] == "good"
    assert it["text"] == ("Va 1-1 en el grupo: si gana pasa, o queda en un empate a victorias; "
                          "si pierde queda afuera salvo un empate a victorias")


def test_group_already_through_and_already_out():
    # 20-nov: Alcaraz 2-0, Medvedev 1-1, Tiafoe 1-1, Cobolli 0-2; Medvedev-Tiafoe still to play
    results = [("Alcaraz", "Tiafoe"), ("Medvedev", "Cobolli"), ("Alcaraz", "Medvedev"), ("Tiafoe", "Cobolli")]
    remaining = [("Medvedev", "Tiafoe")]
    assert "pase lo que pase" in stakes_item((2, 0), group_stakes(results, remaining, "Alcaraz", "Cobolli"))["text"]
    out = stakes_item((0, 2), group_stakes(results, remaining, "Cobolli", "Alcaraz"))
    assert out["tone"] == "bad" and "eliminado" in out["text"]
    # Medvedev-Tiafoe with Alcaraz-Cobolli still to play: winner through, loser out
    final = group_stakes(results, [("Alcaraz", "Cobolli")], "Medvedev", "Tiafoe")
    assert final == {"win": {"in"}, "lose": {"out"}}
    assert stakes_item((1, 1), final)["text"] == "Va 1-1 en el grupo: si gana pasa a semis; si pierde queda afuera"


# --- news ---

def test_news_items_take_stakes_and_coach_from_the_analysis_or_the_headlines():
    news = {
        "player1": [{"factor": "en_juego", "note": "a una victoria de semifinales", "headline": "h1"},
                    {"factor": "lesion", "note": "molestia", "headline": "h2"}],
        "player2": [],
        "latest": {"player1": [], "player2": [{"headline": "Shelton, with new coach Ferrero, beats Fils", "source": "ATP"}]},
    }
    p1 = news_items(news, "player1")
    assert [i["key"] for i in p1] == ["stakes_news"]
    p2 = news_items(news, "player2")
    assert p2[0]["key"] == "coach" and "Ferrero" in p2[0]["text"]
    assert news_items(None, "player1") == []
