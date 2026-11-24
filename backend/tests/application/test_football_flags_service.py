from src.application import football_flags_service as ff

OK = {"hasCurrent": True, "currentMatches": 12, "lastEarlier": "2526", "homeMatches": 10, "awayMatches": 10}


def test_a_team_back_after_years_is_flagged_as_recently_promoted():
    stale = {"hasCurrent": False, "currentMatches": 0, "lastEarlier": "1112", "homeMatches": 0, "awayMatches": 0}
    flags = ff.build_flags("Levante", "Racing", "La Liga", "2627", OK, stale, 3.61, 1.35, True, True)
    keys = [f["key"] for f in flags]
    assert "promoted" in keys and "extreme_goals" in keys
    assert any("2011-12" in f["text"] for f in flags if f["key"] == "promoted")


def test_a_team_with_no_data_at_all_is_flagged():
    nothing = {"hasCurrent": False, "currentMatches": 0, "lastEarlier": None, "homeMatches": 0, "awayMatches": 0}
    assert [f["key"] for f in ff.build_flags("A", "B", "La Liga", "2627", nothing, OK, 1.4, 1.1, True, True)] == ["no_history"]


def test_a_normal_match_has_no_warning_and_a_cup_or_missing_price_is_only_info():
    assert ff.build_flags("A", "B", "La Liga", "2627", OK, OK, 1.5, 1.1, True, True) == []
    flags = ff.build_flags("A", "B", "Champions League", "2627", OK, OK, 1.5, 1.1, False, True)
    assert {f["key"] for f in flags} == {"cup", "no_price"} and all(f["level"] == "info" for f in flags)


def test_few_matches_this_season_is_info():
    new = {"hasCurrent": True, "currentMatches": 13, "lastEarlier": "2526", "homeMatches": 7, "awayMatches": 6}
    flags = ff.build_flags("A", "B", "La Liga", "2627", new, OK, 1.5, 1.1, True, True)
    assert [f["key"] for f in flags] == ["few_matches"] and flags[0]["level"] == "info"
