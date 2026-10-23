"""Tests for the player news section (headline filtering and model output cleaning)."""
from datetime import datetime, timedelta, timezone

from src.application import player_news_service as pn


def test_surname_drops_initials():
    assert pn.surname("Fritz T.") == "Fritz"
    assert pn.surname("J-L. Struff") == "Struff"
    assert pn.surname("Carreno-Busta P.") == "Carreno-Busta"
    assert pn.mentions("Carreño Busta se retira en Lyon", "Carreno-Busta P.")


def test_score_pages_and_betting_markets_are_noise():
    assert pn.is_noise("Daniel Altmaier vs Titouan Droguet EN DIRECTO 20/10/2026", "Flashscore.es")
    assert pn.is_noise("October 23, 2026: Altmaier vs Fritz: Total Games Tennis Prediction Market", "Robinhood")
    assert pn.is_noise("Arthur Fils v Alex Michelsen (23/10/2026)", "Flashscore.com")
    assert pn.is_noise("Arthur Fils vs Alex Michelsen · Quarterfinal · ATP Brussels", "Tennis.com")
    assert pn.is_noise("How to watch Michelsen vs. Goffin on live streaming in Brussels", "Tennis Tonic")
    assert not pn.is_noise("Fritz says knee feels better ahead of Lyon quarterfinal", "ATP Tour")
    assert not pn.is_noise("Munar, obligado a retirarse por culpa de su espalda antes de medirse contra Fils", "Eurosport")


def test_model_rows_must_point_at_a_real_headline():
    now = datetime(2026, 10, 22, 15, tzinfo=timezone.utc)
    items = [{"title": "Fritz knee", "source": "ATP Tour", "link": "https://x", "published": now}]
    raw = [
        {"i": 0, "factor": "lesion", "impacto": "negativo", "nota": "Molestia en la rodilla."},
        {"i": 0, "factor": "lesion"},          # repeated
        {"i": 7, "factor": "personal"},        # no such headline: invented
        {"factor": "local"},                   # no index
    ]
    out = pn.clean_items(raw, items)

    assert len(out) == 1
    assert out[0]["factor"] == "lesion" and out[0]["impact"] == "negativo" and out[0]["link"] == "https://x"
    assert pn.clean_items("nothing", items) == []
    assert len(pn.clean_items({"nombre": "Fritz T.", "titulares": raw}, items)) == 1


def test_news_goes_stale_faster_close_to_the_start():
    now = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
    fetched = {"fetchedAt": (now - timedelta(minutes=90)).isoformat()}

    assert not pn.is_stale(fetched, now + timedelta(hours=10), now)
    assert pn.is_stale(fetched, now + timedelta(hours=2), now)
    assert pn.is_stale(None, now + timedelta(hours=10), now)
