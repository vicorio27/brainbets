from datetime import datetime

from src.application import football_collect_service as fc
from src.timezone import BOGOTA_TZ


def fixture(status="NS", home="Manchester City", away="Real Betis", league=39, goals=(None, None)):
    return {"fixture": {"id": 99, "date": "2026-11-24T20:00:00+00:00", "status": {"short": status}},
            "league": {"id": league, "season": 2026, "round": "Regular Season - 12"},
            "teams": {"home": {"name": home}, "away": {"name": away}},
            "goals": {"home": goals[0], "away": goals[1]}}


def bet(name, vals):
    return {"name": name, "values": [{"value": k, "odd": v} for k, v in vals]}


ODDS = {"bookmakers": [
    {"name": "Bet365", "bets": [bet("Match Winner", [("Home", "1.5"), ("Draw", "4"), ("Away", "6")]),
                                bet("Goals Over/Under", [("Over 2.5", "1.9"), ("Under 2.5", "1.95"), ("Over 9.5", "9")]),
                                bet("Both Teams Score", [("Yes", "1.8"), ("No", "2.0")])]},
    {"name": "Pinnacle", "bets": [bet("Goals Over/Under", [("Over 2.5", "1.92"), ("Under 2.5", "1.98")])]},
]}


def test_names_and_seasons_follow_the_historical_files():
    assert fc.team_name("Manchester City") == "Man City"
    assert fc.team_name("Atletico Madrid") == "Ath Madrid"
    assert fc.team_name("Arsenal") == "Arsenal"
    assert fc.season_code(2026) == "2627" and fc.season_code(2024) == "2425"


def test_status_mapping():
    assert [fc.status_of(s) for s in ("NS", "1H", "HT", "FT", "AET", "PST", "CANC")] == [
        "SCHEDULED", "LIVE", "LIVE", "FINISHED", "FINISHED", "CANCELLED", "CANCELLED"]


def test_only_the_two_leagues_and_bogota_time():
    raw = fc.to_raw(fixture())
    assert raw["league"] == "Premier League" and raw["homeTeam"] == "Man City" and raw["awayTeam"] == "Betis"
    assert (raw["eventDate"], raw["eventTime"]) == ("2026-11-24", "15:00")
    assert fc.to_raw(fixture(league=61)) is None


def test_score_only_when_finished():
    assert "homeScore" not in fc.to_raw(fixture(goals=(0, 0)))
    done = fc.to_raw(fixture("FT", goals=(2, 1)))
    assert (done["homeScore"], done["awayScore"]) == (2, 1)


def test_prices_pick_pinnacle_first_and_keep_every_book():
    books = fc.book_prices(ODDS)
    assert "overUnder" in books["Pinnacle"] and "9.5" not in books["Bet365"]["overUnder"]
    m = fc.pick_markets(books)
    assert m["overUnder"]["2.5"] == {"over": 1.92, "under": 1.98}      # Pinnacle wins the priority
    assert m["matchWinner"]["draw"] == 4.0 and m["btts"]["yes"] == 1.8  # Pinnacle lacks those -> Bet365
    assert set(m["books"]["overUnder25"]) == {"Pinnacle", "Bet365"}
    assert fc.pick_markets({}) is None


def test_prices_feed_the_engine_fields():
    raw = fc.to_raw(fixture(), fc.pick_markets(fc.book_prices(ODDS)))
    assert (raw["homeOdds"], raw["drawOdds"], raw["awayOdds"]) == (1.5, 4.0, 6.0)


def test_plan_full_once_a_day_then_only_when_something_is_on():
    t = datetime(2026, 11, 24, 9, 0, tzinfo=BOGOTA_TZ)
    p = fc.plan(t, {}, False)
    assert p["full"] and p["days"] == ["2026-11-23", "2026-11-24", "2026-11-25"]
    again = fc.plan(t, {"full_day": "2026-11-24"}, False)
    assert not again["full"] and again["days"] == []
    assert fc.plan(t, {"full_day": "2026-11-24"}, True)["days"] == ["2026-11-24"]
    assert not fc.plan(datetime(2026, 11, 24, 1, 0, tzinfo=BOGOTA_TZ), {}, False)["full"]   # before 03:00


def test_extra_prices_keep_double_chance_halves_and_corners():
    from src.application.football_collect_service import extra_prices
    item = {"bookmakers": [{"name": "Bet365", "bets": [
        {"name": "Double Chance", "values": [{"value": "Home/Draw", "odd": "1.36"}, {"value": "Home/Away", "odd": "1.30"}, {"value": "Draw/Away", "odd": "1.57"}]},
        {"name": "Goals Over/Under First Half", "values": [{"value": "Over 0.5", "odd": "1.36"}, {"value": "Under 0.5", "odd": "3.00"}]},
        {"name": "Corners Over Under", "values": [{"value": "Over 10.5", "odd": "1.82"}, {"value": "Under 10.5", "odd": "1.98"}]},
    ]}]}
    out = extra_prices(item)
    assert out["doubleChance"] == {"1X": 1.36, "12": 1.3, "X2": 1.57}
    assert out["firstHalf"]["0.5"] == {"over": 1.36, "under": 3.0}
    assert out["corners"]["10.5"]["over"] == 1.82
    assert extra_prices({"bookmakers": []}) is None
