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


def test_what_is_at_stake_goes_first_and_survives_the_noise_filter():
    # 29-oct: the No. 1 line was headline 30 of Zverev's week and fell outside the 25 newest
    t0 = datetime(2026, 10, 29, 15, tzinfo=timezone.utc)
    filler = [{"title": f"Zverev w{i}a w{i}b w{i}c", "source": "Tennis World", "link": "x",
               "published": t0 - timedelta(hours=i)} for i in range(60)]
    stake = {"title": "Zverev quedó a una victoria de ser el N°1 del mundo", "source": "ESPN Deportes",
             "link": "y", "published": t0 - timedelta(days=2)}
    picked = pn.select_headlines(filler + [stake], "Zverev A.")
    assert stake in picked and len(picked) == pn.MAX_HEADLINES
    assert pn.is_stakes("Alexander Zverev explains what being world number one means to him")
    assert not pn.is_noise("Landaluce no se achica en Viena ante el futuro número uno del tenis mundial", "Flashscore.es")
    assert pn.is_noise("Zverev vs Fery: will he be No. 1? Prediction Market", "Robinhood")
    assert pn.is_noise("Zverev A. vs Fery A. pronostico y cuotas: número 1 en juego", "Tenis Hoy")


def test_a_list_wrapped_under_any_key_is_read():
    now = datetime(2026, 10, 29, 15, tzinfo=timezone.utc)
    items = [{"title": "Zverev, a una victoria del N°1", "source": "ESPN", "link": "z", "published": now}]
    out = pn.clean_items({"LISTA": [{"i": 0, "factor": "en_juego", "impacto": "positivo", "nota": "x"}]}, items)
    assert len(out) == 1 and out[0]["factor"] == "en_juego"


def test_the_same_story_from_another_outlet_or_language_is_kept_once():
    t0 = datetime(2026, 10, 29, 20, tzinfo=timezone.utc)
    titles = [
        "ATP roundup: Alexander Zverev clinches world No. 1 ranking",
        "Germany's Alexander Zverev clinches tennis No. 1 ranking",
        "Alexander Zverev's first No. 1 ranking to be confirmed Monday with win in Vienna",
        "Alexander Zverev's first No. 1 ranking will be confirmed Monday thanks to win in Vienna",
        "Es oficial: Alexander Zverev será el No.1 del tenis mundial desde el lunes",
        "Alexander Zverev será el nuevo número uno del mundo desde el próximo lunes",
        "Zverev saves 4 MPs, survives Landaluce test in Vienna",
        "Alexander Zverev confirms his holiday destination and how long he will rest",
    ]
    items = [{"title": t, "source": "S", "link": str(i), "published": t0 - timedelta(minutes=i)}
             for i, t in enumerate(titles)]
    kept = [it["title"] for it in pn.select_headlines(items, "Zverev A.")]
    assert kept == [titles[0], titles[2], titles[4], titles[6], titles[7]]


def test_victoria_and_triunfo_tell_the_same_story():
    a = pn.headline_signature("Zverev ganó el partido del día, salvó cuatro match points y quedó a una victoria de ser el N°1 del mundo", "Zverev A.")
    b = pn.headline_signature("ATP 500 Viena 2026: Alexander Zverev salva cuatro match points y queda a un triunfo del N.º 1 del mundo", "Zverev A.")
    assert pn.same_story(a, b)
