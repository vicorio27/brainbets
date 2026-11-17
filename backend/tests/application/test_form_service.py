"""Recent level vs the player's own usual level (form_service)."""
from src.application import form_service as fs


def row(won=True, sgw=10, sgt=12, ft=40, fw=30, st=24, spt=64, aces=6, set1=True, rgw=3, rgt=12):
    return {"won": won, "set1": set1, "sgw": sgw, "sgt": sgt, "rgw": rgw, "rgt": rgt,
            "fw": fw, "ft": ft, "st": st, "spt": spt, "aces": aces}


def test_match_row_reads_the_player_side():
    stats = {"sets": [{"p1": 4, "p2": 6}], "homeAces": 3, "awayAces": 9,
             "serve": {"away": {"serveGamesWon": 9, "serveGamesTotal": 10, "firstServeWon": 25,
                                "firstServeTotal": 30, "secondServeTotal": 20, "servePtsTotal": 50}}}
    r = fs.match_row(stats, is_home=False, won=True)
    assert r["set1"] is True and r["aces"] == 9 and r["sgw"] == 9 and r["won"]


def test_needs_enough_matches():
    assert fs.form_report([row()] * 10) is None


def test_a_top_player_playing_badly_is_called_out():
    bad = [row(won=False, sgw=7, sgt=12, st=34, aces=2, set1=False) for _ in range(5)]
    usual = [row() for _ in range(20)]
    rep = fs.form_report(bad + usual, ranking=1)
    assert rep["level"] == "mal"
    assert rep["headline"].startswith("Es el #1 del mundo, pero viene jugando por debajo de su nivel")
    worse = {m["key"] for m in rep["metrics"] if m["trend"] == "peor"}
    assert {"hold", "firstIn", "aces", "set1", "wins"} <= worse


def test_same_level_is_normal():
    rep = fs.form_report([row() for _ in range(25)], ranking=5)
    assert rep["level"] == "normal" and all(m["trend"] is None for m in rep["metrics"])


def test_playing_well():
    good = [row(sgw=12, sgt=12, rgw=6, rgt=12) for _ in range(5)]
    rep = fs.form_report(good + [row() for _ in range(20)], ranking=80)
    assert rep["level"] == "bien" and rep["headline"].startswith("Es el #80 del mundo, pero viene jugando por encima")
