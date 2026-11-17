"""Price history and movement (odds_movement_service)."""
from src.application import odds_movement_service as om


def test_append_skips_an_unchanged_price():
    mk = {"matchWinner": {"p1": 1.5, "p2": 2.6}}
    h = om.append_snapshot(None, mk, "t0")
    h = om.append_snapshot(h, mk, "t1")
    assert len(h) == 1
    h = om.append_snapshot(h, {"matchWinner": {"p1": 1.4, "p2": 2.9}}, "t2")
    assert [s["at"] for s in h] == ["t0", "t2"]


def test_movement_reports_the_change_in_fair_probability():
    h = [{"at": "t0", "matchWinner": {"p1": 2.0, "p2": 2.0}}, {"at": "t1", "matchWinner": {"p1": 1.6, "p2": 2.5}}]
    moves = {m["side"]: m for m in om.movement(h, {"p1": "A", "p2": "B"})}
    assert moves["p1"]["fromProb"] == 0.5 and moves["p1"]["delta"] > 0.1 and moves["p1"]["moved"]
    assert moves["p2"]["delta"] < 0
    assert om.movement(h[:1], {}) == []
