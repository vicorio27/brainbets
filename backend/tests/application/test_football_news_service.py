from datetime import datetime, timezone

from src.application import football_news_service as fn


def item(title, source="Marca", hours=1):
    return {"title": title, "source": source, "link": "http://x", "published": datetime(2026, 11, 24, 12 - hours, tzinfo=timezone.utc)}


def test_search_name_goes_back_to_the_name_the_press_uses():
    assert fn.search_name("Man City") == "Manchester City" and fn.search_name("Ath Madrid") == "Atletico Madrid"
    assert fn.search_name("Brentford") == "Brentford"


def test_headlines_are_tagged_by_what_matters_before_a_match():
    assert fn.tag_headline("Chelsea: Palmer ruled out with a hamstring injury") == ["lesion"]
    assert "sancion" in fn.tag_headline("Rodri suspended for the derby after a red card")
    assert "entrenador" in fn.tag_headline("Sacked: the club parts ways with its manager")
    assert fn.tag_headline("Great weather in Madrid") == []


def test_only_headlines_that_mention_the_team_survive_and_repeats_collapse():
    names = fn.aliases_of("Man City")
    items = [item("Manchester City: Haaland doubtful for Napoli with an ankle injury"),
             item("Manchester City: Haaland doubtful for Napoli with an ankle injury, says Guardiola", hours=2),
             item("Real Madrid sign a new winger"), item("Man City - Napoli: predictions and odds", "oddschecker")]
    out = fn.select(items, names)
    assert len(out) == 1 and out[0]["tags"] == ["lesion"]


def test_view_keeps_a_tagged_headline_over_newer_untagged_ones():
    items = [{**item(f"Club talks number {i}", hours=0), "tags": []} for i in range(6)] + \
            [{**item("Star striker ruled out for the game", hours=5), "tags": ["lesion"]}]
    shown = fn.view(items)
    assert len(shown) == fn.SHOWN and any(s["tags"] == ["lesion"] for s in shown)


def test_where_to_watch_odds_and_previews_are_not_news_even_with_a_tag():
    names = fn.aliases_of("Real Madrid")
    items = [item("Real Madrid vs PSV: Champions League pregame, form and odds", "Sofascore"),
             item("¿A qué hora se juega el Real Madrid - PSV? TV, horario, dónde y cómo ver la Champions", "Diario AS"),
             item("Real Madrid: Mbappe ruled out of the PSV game with a hamstring injury", "Marca")]
    out = fn.select(items, names)
    assert [o["tags"] for o in out] == [["lesion"]]
