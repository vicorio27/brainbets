from datetime import datetime, timezone

from src.application.matchup_service import build


def meet(year, won, sf, sa, tbf=0, tba=0, sgw=None, sgt=10):
    return {"date": datetime(year, 6, 1, tzinfo=timezone.utc), "won": won, "sets_for": sf, "sets_against": sa,
            "tb_for": tbf, "tb_against": tba, "serve": {"sgw": sgw, "sgt": sgt} if sgw is not None else None,
            "serve_rival": {"sgw": 9, "sgt": 10}}


def test_a_player_who_rarely_beats_this_rival_says_so_with_tiebreaks_and_serve():
    ms = [meet(2022, False, 0, 2, 0, 1, 6), meet(2023, True, 2, 1, 1, 0, 7), meet(2024, False, 1, 2, 0, 2, 6),
          meet(2025, False, 0, 2, 0, 0, 5), meet(2026, False, 0, 2, 0, 0, 6)]
    got = build("Zverev A.", "Alcaraz C.", ms, 0.92, 0.88)
    a = got["p1"]
    assert a["record"] == "1-4"
    assert a["lines"][0] == "Zverev A. 1-4 contra Alcaraz (desde 2024: 0-3); sets 3-9; 3 derrotas en 2 sets"
    assert "Tiebreaks contra Alcaraz: Zverev A. 1-3" in a["lines"]
    assert a["notes"][0] == "No le ha ido bien contra Alcaraz: ganó 1 de 5"
    assert any(n.startswith("Pierde más tiebreaks") for n in a["notes"])
    assert any(n.startswith("Su saque baja contra Alcaraz: 60%") for n in a["notes"])
    assert got["p2"]["record"] == "4-1" and got["p2"]["notes"][0].startswith("Le ha ido bien contra Zverev")


def test_too_few_meetings_say_nothing():
    assert build("A", "B", [meet(2024, True, 2, 0), meet(2025, False, 0, 2)], None, None) is None
