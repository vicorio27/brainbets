from src.application import football_corners_lab_service as cl


def test_main_line_is_the_most_balanced_half_line():
    lines = {"8.5": {"over": 1.5, "under": 2.5}, "9.5": {"over": 1.9, "under": 1.9},
             "10": {"over": 1.9, "under": 1.9}, "10.5": {"over": 2.4, "under": 1.55}}
    line, o, u, p = cl.main_line(lines)
    assert line == 9.5 and round(p, 3) == 0.5
    assert cl.main_line({}) is None and cl.main_line({"9": {"over": 1.9, "under": 1.9}}) is None


def test_expected_corners_needs_history_and_shrinks_to_the_league():
    assert cl.expected_corners([(5, 4)], [(5, 4)], 5.5, 4.5) is None
    avg = cl.expected_corners([(5.5, 4.5)] * 20, [(4.5, 5.5)] * 20, 5.5, 4.5)
    assert abs(avg - 10.0) < 0.2
    # a team that wins many corners and a rival that concedes many: above the league mean
    high = cl.expected_corners([(9, 4)] * 40, [(4, 8)] * 40, 5.5, 4.5)
    assert high > 11


def test_p_over_falls_with_the_line():
    assert cl.p_over(10, 8.5) > cl.p_over(10, 10.5) > cl.p_over(10, 12.5)


def test_a_small_sample_only_gathers():
    rows = [{"date": "2026-11-25", "x": [0.1], "won": 1, "pMarket": 0.5, "pModel": 0.55, "odds1": 1.9, "odds2": 1.9}] * 5
    r = cl.build_report(rows)
    assert r["verdict"]["level"] == "juntando_muestra" and r["weights"] is None
