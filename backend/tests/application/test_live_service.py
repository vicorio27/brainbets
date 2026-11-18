"""Live reading of a followed match (live_service), with events shaped like api-tennis get_livescore."""
from src.application import live_service as ls

NAMES = {"p1": "Fils", "p2": "Jodar"}


def stat(key, name, value=None, won=None, total=None):
    return {"player_key": key, "stat_period": "match", "stat_name": name,
            "stat_value": value, "stat_won": won, "stat_total": total}


def event(p1_pts, p2_pts, aces=(0, 0), df=(0, 0), winners=(0, 0), ue=(0, 0), sets=((1, 0),), pbp=None, status="Set 1", **extra):
    st = []
    for key, i in ((1, 0), (2, 1)):
        pts = (p1_pts, p2_pts)[i]
        st += [stat(key, "Aces", str(aces[i])), stat(key, "Double Faults", str(df[i])),
               stat(key, "Winners", str(winners[i])), stat(key, "Unforced errors", str(ue[i])),
               stat(key, "Total Points Won", won=pts, total=p1_pts + p2_pts)]
        for k, v in extra.get("more", {}).get(i, {}).items():
            st.append(stat(key, k, **v))
    return {"first_player_key": 1, "second_player_key": 2, "event_status": status, "event_serve": "First Player",
            "event_game_result": "15 - 0", "event_final_result": "0 - 0",
            "scores": [{"score_first": str(a), "score_second": str(b)} for a, b in sets],
            "pointbypoint": pbp or [], "statistics": st}


def test_parse_reads_both_sides():
    r = ls.parse_event(event(10, 7, aces=(2, 1), winners=(5, 3)))
    assert r["pointsPlayed"] == 17 and r["pointsWon"] == {"p1": 10, "p2": 7}
    assert r["stats"]["p1"]["aces"] == 2 and r["stats"]["p2"]["winners"] == 3 and r["server"] == "p1"


def test_one_point_is_named_by_what_moved():
    prev = ls.parse_event(event(10, 7, ue=(1, 2)))
    assert ls.point_events(prev, ls.parse_event(event(11, 7, aces=(1, 0), ue=(1, 2))), NAMES) == ["Ace de Fils."]
    assert ls.point_events(prev, ls.parse_event(event(10, 8, ue=(2, 2))), NAMES) == [
        "Error no forzado de Fils: punto regalado a Jodar."]
    assert ls.point_events(prev, ls.parse_event(event(10, 8, winners=(0, 1), ue=(1, 2))), NAMES) == [
        "Winner de Jodar: punto agresivo."]
    assert ls.point_events(prev, ls.parse_event(event(10, 8, ue=(1, 2))), NAMES) == [
        "Punto para Jodar (error forzado o peloteo largo)."]


def test_several_points_are_summarised_and_a_break_is_called():
    prev = ls.parse_event(event(10, 7))
    pbp = [{"set_number": "Set 1", "number_game": "4", "player_served": "First Player", "serve_lost": "First Player"}]
    out = ls.point_events(prev, ls.parse_event(event(10, 10, winners=(0, 2), pbp=pbp)), NAMES)
    assert out[0] == "Últimos 3 puntos: Fils ganó 0; Jodar ganó 3 (2 winner(s))."
    assert out[1].startswith("¡Break! Jodar le quebró el saque a Fils")


def test_general_read_names_the_aggressive_player():
    cur = ls.parse_event(event(30, 25, winners=(12, 3), ue=(6, 4), aces=(2, 1)))
    items = ls.general_read(cur, NAMES)["items"]
    assert items[0].startswith("Fils está siendo más agresivo")
    assert any(i.startswith("A Fils le funciona: 12 winners por 6") for i in items)


def test_too_early_and_no_shot_data():
    assert "Muy pronto" in ls.general_read(ls.parse_event(event(5, 4)), NAMES)["items"][0]
    ev = event(30, 25)
    ev["statistics"] = [s for s in ev["statistics"] if s["stat_name"] not in ("Winners", "Unforced errors")]
    items = ls.general_read(ls.parse_event(ev), NAMES)["items"]
    assert items[-1].startswith("El feed no trae winners")


def test_first_serve_against_his_usual_level():
    more = {0: {"1st serve points won": {"won": 10, "total": 13}, "2nd serve points won": {"won": 6, "total": 12}}}
    cur = ls.parse_event(event(30, 25, more=more))
    items = ls.general_read(cur, NAMES, {"p1": {"firstIn": 0.68}})["items"]
    assert any(i.startswith("Fils mete menos primeros de lo normal: 52% (lo normal en él: 68%)") for i in items)


# Real point by point: Fils vs Jodar, ATP Finals, 17-nov-2026 (4-6 6-2 6-2), from get_fixtures.
import json as _json
from pathlib import Path as _Path

_PBP = _json.loads((_Path(__file__).parent / "fils_jodar_pbp.json").read_text())
_FJ = {"p1": "Fils", "p2": "Jodar"}


def test_pressure_matches_the_official_match_stats():
    pr = ls.pressure(_PBP)
    assert (pr["p1"]["points"], pr["p2"]["points"]) == (85, 68)         # Total Points Won 85/153
    assert (pr["p1"]["serveWon"], pr["p1"]["servePlayed"]) == (50, 66)  # Service Points Won 50/66
    assert pr["p1"]["bpFaced"] == 2 and pr["p2"]["broken"] == 4


def test_at_4_4_fils_is_playing_better_though_the_score_is_level():
    set1 = [g for g in _PBP if g["set_number"] == "Set 1"]
    out = ls.who_is_better(set1[:8], _FJ)
    assert out[0].startswith("Juega mejor Fils: saca más cómodo y presiona más el saque de Jodar")
    assert out[0].endswith("aunque el marcador va parejo.")


def test_when_the_pressing_player_wins_fewer_points_it_is_called_level():
    set1 = [g for g in _PBP if g["set_number"] == "Set 1"]
    assert ls.who_is_better(set1[:10], _FJ)[0].startswith("Parejo, con matices")
    assert ls.leader(set1[:10]) == "p2"
