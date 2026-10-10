"""Tests for the bankroll ("caja") simulation math.

Only the pure part of `src/application/bankroll_service.py` is exercised
here: `load_bets`/`simulate` need a database, the staking and growth math
does not.
"""
from datetime import date, timedelta

import pytest

from src.application import bankroll_service as bs
from src.application.bankroll_service import Bet, StakePlan


def make_bet(day, won, odds=2.0, probability=0.6, market="Match Winner", sport="tennis"):
    return Bet(
        day=date(2026, 1, 1) + timedelta(days=day - 1),
        sport=sport,
        market=market,
        odds=odds,
        won=won,
        probability=probability,
        confidence=int(probability * 100),
    )


# ----------------------------------------------------------------------
# Staking
# ----------------------------------------------------------------------
def test_percent_strategy_compounds_on_the_current_bankroll():
    plan = StakePlan(strategy="percent", stake_pct=10.0)
    bet = make_bet(1, won=True)

    assert bs._stake_for(bet, bankroll=100.0, initial=100.0, plan=plan) == pytest.approx(10.0)
    assert bs._stake_for(bet, bankroll=200.0, initial=100.0, plan=plan) == pytest.approx(20.0)


def test_flat_strategy_keeps_the_stake_tied_to_the_initial_bankroll():
    plan = StakePlan(strategy="flat", stake_pct=10.0)
    bet = make_bet(1, won=True)

    assert bs._stake_for(bet, bankroll=200.0, initial=100.0, plan=plan) == pytest.approx(10.0)


def test_kelly_stake_follows_the_edge_and_is_zero_without_one():
    plan = StakePlan(strategy="kelly", stake_pct=2.0, kelly_multiplier=1.0, max_stake_pct=50.0)
    # p=0.6 at odds 2.0 -> b=1, f = (1*0.6 - 0.4)/1 = 0.20
    edge = make_bet(1, won=True, odds=2.0, probability=0.6)
    assert bs._stake_for(edge, bankroll=100.0, initial=100.0, plan=plan) == pytest.approx(20.0)

    # p=0.4 at odds 2.0 -> negative Kelly, clipped to no bet
    no_edge = make_bet(1, won=True, odds=2.0, probability=0.4)
    assert bs._stake_for(no_edge, bankroll=100.0, initial=100.0, plan=plan) == 0.0


def test_max_stake_pct_caps_every_strategy():
    plan = StakePlan(strategy="kelly", kelly_multiplier=1.0, max_stake_pct=5.0)
    huge_edge = make_bet(1, won=True, odds=3.0, probability=0.9)

    assert bs._stake_for(huge_edge, bankroll=100.0, initial=100.0, plan=plan) == pytest.approx(5.0)


def test_many_bets_on_one_day_are_scaled_to_the_daily_exposure_limit():
    """Ten 10%-of-bankroll picks on the same day cannot risk 100% of the caja."""
    plan = StakePlan(strategy="percent", stake_pct=10.0, max_stake_pct=10.0)
    day_bets = [make_bet(1, won=False) for _ in range(10)]

    staked, profit = bs._settle_day(day_bets, bankroll=100.0, initial=100.0, plan=plan)

    assert staked == pytest.approx(100.0 * bs.MAX_DAILY_EXPOSURE)
    assert profit == pytest.approx(-100.0 * bs.MAX_DAILY_EXPOSURE)


def test_same_day_bets_are_all_funded_at_the_day_start_bankroll():
    """A winning pick does not increase the stake of another pick that day."""
    plan = StakePlan(strategy="percent", stake_pct=10.0)
    day_bets = [make_bet(1, won=True), make_bet(1, won=True)]

    staked, profit = bs._settle_day(day_bets, bankroll=100.0, initial=100.0, plan=plan)

    assert staked == pytest.approx(20.0)      # 10 + 10, not 10 + 11
    assert profit == pytest.approx(20.0)      # both at odds 2.0


# ----------------------------------------------------------------------
# Backtest
# ----------------------------------------------------------------------
def test_backtest_compounds_across_days():
    plan = StakePlan(strategy="percent", stake_pct=10.0)
    bets = [make_bet(1, won=True), make_bet(2, won=True)]

    result = bs.simulate_bankroll(bets, initial=100.0, plan=plan)

    # day 1: 100 + 10 = 110; day 2: 110 + 11 = 121
    assert result["final"] == pytest.approx(121.0)
    assert result["multiple"] == pytest.approx(1.21)
    assert result["winRate"] == 100.0
    assert result["daysSpan"] == 2
    assert [p["bankroll"] for p in result["curve"]] == [110.0, 121.0]


def test_backtest_reports_losses_drawdown_and_yield():
    plan = StakePlan(strategy="flat", stake_pct=10.0)
    bets = [make_bet(1, won=True), make_bet(2, won=False), make_bet(3, won=False)]

    result = bs.simulate_bankroll(bets, initial=100.0, plan=plan)

    # +10, -10, -10
    assert result["final"] == pytest.approx(90.0)
    assert result["profit"] == pytest.approx(-10.0)
    assert result["staked"] == pytest.approx(30.0)
    assert result["yield"] == pytest.approx(-33.33, abs=0.01)
    assert result["maxDrawdown"] == pytest.approx(18.18, abs=0.01)  # 110 -> 90
    assert result["winRate"] == pytest.approx(33.33, abs=0.01)


def test_backtest_stops_when_the_caja_is_busted():
    plan = StakePlan(strategy="percent", stake_pct=50.0, max_stake_pct=50.0)
    bets = [make_bet(d, won=False) for d in range(1, 11)]

    result = bs.simulate_bankroll(bets, initial=100.0, plan=plan)

    assert result["busted"] is True
    assert result["settledBets"] < len(bets)
    assert result["final"] <= 100.0 * bs.RUIN_MULTIPLE


def test_empty_history_is_not_an_error():
    result = bs.simulate_bankroll([], initial=250.0, plan=StakePlan())

    assert result["bets"] == 0
    assert result["final"] == 250.0
    assert result["curve"] == []
    assert result["dailyGrowth"] is None


# ----------------------------------------------------------------------
# Projection
# ----------------------------------------------------------------------
def test_projection_doubling_time_matches_the_daily_growth():
    plan = StakePlan(strategy="percent", stake_pct=10.0)
    bets = [make_bet(d, won=True) for d in range(1, 8)]  # 7 straight winners

    backtest = bs.simulate_bankroll(bets, initial=100.0, plan=plan)
    projection = bs.project_to_target(backtest, target_multiple=2.0)

    assert projection["reachable"] is True
    # 10% per day compounded doubles in log(2)/log(1.1) ~ 7.27 days
    assert projection["daysToTarget"] == pytest.approx(7.3, abs=0.1)
    assert projection["targetAmount"] == 200.0
    assert projection["etaDate"] is not None


def test_projection_refuses_to_extrapolate_a_losing_history():
    plan = StakePlan(strategy="percent", stake_pct=10.0)
    bets = [make_bet(d, won=False) for d in range(1, 5)]

    projection = bs.project_to_target(
        bs.simulate_bankroll(bets, initial=100.0, plan=plan), target_multiple=2.0
    )

    assert projection["reachable"] is False
    assert projection["note"] == "sin_ventaja"
    assert projection["daysToTarget"] is None


def test_projection_flags_a_target_the_history_already_passed():
    plan = StakePlan(strategy="percent", stake_pct=50.0, max_stake_pct=50.0)
    bets = [make_bet(d, won=True) for d in range(1, 5)]

    projection = bs.project_to_target(
        bs.simulate_bankroll(bets, initial=100.0, plan=plan), target_multiple=2.0
    )

    assert projection["note"] == "ya_alcanzado"
    assert projection["daysToTarget"] == 0


def test_projection_without_data_says_so():
    projection = bs.project_to_target(
        bs.simulate_bankroll([], initial=100.0, plan=StakePlan()), target_multiple=2.0
    )

    assert projection["note"] == "sin_datos"
    assert projection["reachable"] is False


# ----------------------------------------------------------------------
# Monte Carlo
# ----------------------------------------------------------------------
def test_monte_carlo_is_deterministic_for_a_given_seed():
    bets = [make_bet(1, won=i % 2 == 0) for i in range(20)]
    kwargs = dict(
        initial=100.0,
        plan=StakePlan(strategy="percent", stake_pct=5.0),
        target_multiple=2.0,
        bets_per_day=2.0,
        sims=50,
        horizon_days=60,
    )

    assert bs.monte_carlo(bets, **kwargs) == bs.monte_carlo(bets, **kwargs)


def test_monte_carlo_always_doubles_a_history_that_only_wins():
    bets = [make_bet(1, won=True, odds=2.0) for _ in range(10)]

    mc = bs.monte_carlo(
        bets,
        initial=100.0,
        plan=StakePlan(strategy="percent", stake_pct=10.0),
        target_multiple=2.0,
        bets_per_day=1.0,
        sims=50,
        horizon_days=60,
    )

    assert mc["probReachTarget"] == 100.0
    assert mc["probRuin"] == 0.0
    assert mc["daysP50"] == pytest.approx(8.0)  # 1.1**8 = 2.14


def test_monte_carlo_ruins_a_history_that_only_loses():
    bets = [make_bet(1, won=False) for _ in range(10)]

    mc = bs.monte_carlo(
        bets,
        initial=100.0,
        plan=StakePlan(strategy="percent", stake_pct=20.0, max_stake_pct=20.0),
        target_multiple=2.0,
        bets_per_day=1.0,
        sims=30,
        horizon_days=120,
    )

    assert mc["probReachTarget"] == 0.0
    assert mc["probRuin"] == 100.0
    assert mc["daysP50"] is None


def test_monte_carlo_has_no_median_when_most_scenarios_never_arrive():
    # 1 winner in 4 at even odds: a few lucky paths double, most don't.
    bets = [make_bet(1, won=i % 4 == 0) for i in range(40)]

    mc = bs.monte_carlo(
        bets,
        initial=100.0,
        plan=StakePlan(strategy="percent", stake_pct=10.0),
        target_multiple=1.2,
        bets_per_day=1.0,
        sims=200,
        horizon_days=30,
    )

    assert 0.0 < mc["probReachTarget"] < 50.0
    assert mc["daysP50"] is None
    assert mc["daysP50IfReached"] is not None


# ----------------------------------------------------------------------
# Verdict
# ----------------------------------------------------------------------
def _verdict_for(bets, target=2.0, stake_pct=5.0):
    plan = StakePlan(strategy="percent", stake_pct=stake_pct)
    backtest = bs.simulate_bankroll(bets, 100.0, plan)
    projection = bs.project_to_target(backtest, target)
    mc = bs.monte_carlo(
        bets, 100.0, plan, target, bets_per_day=backtest.get("betsPerDay") or 0, sims=100
    )
    return bs.build_verdict(bets, backtest, projection, mc)


def test_verdict_calls_a_short_winning_streak_inconclusive():
    bets = [make_bet(i + 1, won=True) for i in range(10)]

    verdict = _verdict_for(bets, target=1.2)

    assert verdict["level"] == "no_concluyente"
    assert "muestra_chica" in verdict["reasons"]


def test_verdict_calls_a_noisy_small_profit_inconclusive():
    # 52% winners at even odds: the backtest grows, the yield is noise.
    bets = [make_bet(i + 1, won=i % 25 < 13) for i in range(100)]

    verdict = _verdict_for(bets)

    assert verdict["level"] == "no_concluyente"
    assert "yield_no_significativo" in verdict["reasons"]


def test_verdict_recognises_a_large_consistent_edge():
    bets = [make_bet(i + 1, won=i % 5 != 0) for i in range(200)]  # 80% at 2.0

    verdict = _verdict_for(bets)

    assert verdict["level"] in ("edge_real", "ya_alcanzado")
    assert verdict["reasons"] == []
    assert verdict["edge"]["significant"] is True


def test_verdict_says_it_loses_when_the_backtest_shrinks():
    bets = [make_bet(i + 1, won=i % 3 == 0) for i in range(60)]

    assert _verdict_for(bets)["level"] == "pierde"


# ----------------------------------------------------------------------
# Caja per market
# ----------------------------------------------------------------------
def test_caja_by_market_matches_filtering_to_that_market():
    winners = [make_bet(i + 1, won=i % 5 != 0, market="Set 1 Winner") for i in range(60)]
    losers = [make_bet(i + 1, won=i % 3 == 0, market="Match Winner") for i in range(60)]
    plan = StakePlan(strategy="percent", stake_pct=5.0)

    rows = bs.caja_by_market(winners + losers, 100.0, plan, 2.0, sims=50)
    by_market = {r["market"]: r for r in rows}

    alone = bs.simulate_bankroll(winners, 100.0, plan)
    assert by_market["Set 1 Winner"]["final"] == alone["final"]
    assert by_market["Set 1 Winner"]["final"] > 100.0
    assert by_market["Match Winner"]["level"] == "pierde"


def test_caja_by_market_leads_with_the_active_universe_and_flags_paused():
    active = [make_bet(i + 1, won=i % 2 == 0, market="Match Winner") for i in range(40)]
    paused = [make_bet(i + 1, won=False, market="Exact Set Score") for i in range(40)]

    rows = bs.caja_by_market(active + paused, 100.0, StakePlan(), 2.0, sims=20)

    assert rows[0]["market"] is None
    assert rows[0]["bets"] == 40  # paused market stays out of the combined row
    assert rows[-1]["market"] == "Exact Set Score"
    assert rows[-1]["paused"] is True


def test_monte_carlo_without_bets_returns_no_data():
    mc = bs.monte_carlo([], initial=100.0, plan=StakePlan(), target_multiple=2.0, bets_per_day=0)

    assert mc["sims"] == 0
    assert mc["note"] == "sin_datos"


# ----------------------------------------------------------------------
# Per-market breakdown
# ----------------------------------------------------------------------
def test_breakdown_ranks_markets_by_profit_in_flat_units():
    bets = [
        make_bet(1, won=True, odds=2.0, market="Match Winner"),
        make_bet(2, won=True, odds=2.0, market="Match Winner"),
        make_bet(3, won=False, odds=4.0, market="Exact Set Score"),
        make_bet(4, won=False, odds=4.0, market="Exact Set Score"),
    ]

    rows = bs.breakdown_by_market(bets)

    assert [r["market"] for r in rows] == ["Match Winner", "Exact Set Score"]
    assert rows[0]["profitUnits"] == pytest.approx(2.0)
    assert rows[0]["yield"] == pytest.approx(100.0)
    assert rows[1]["profitUnits"] == pytest.approx(-2.0)
    assert rows[1]["winRate"] == 0.0
    # Only 2 bets per market: far below the significance threshold either way.
    assert rows[0]["significant"] is False
    assert rows[1]["significant"] is False


def test_breakdown_flags_a_small_winning_streak_as_not_significant():
    """A believable-looking edge with few bets must not be trusted yet."""
    bets = [make_bet(d, won=True, odds=1.8) for d in range(1, 11)]

    rows = bs.breakdown_by_market(bets)

    assert rows[0]["bets"] == 10
    assert rows[0]["significant"] is False


def test_breakdown_flags_a_large_consistent_edge_as_significant():
    """A real, large, consistent edge with enough bets should pass the bar."""
    # 50 bets, 70% win rate at odds 2.0: a real edge over breakeven (50%).
    bets = [make_bet(d, won=(d % 10 < 7), odds=2.0) for d in range(1, 51)]

    rows = bs.breakdown_by_market(bets)

    assert rows[0]["bets"] == 50
    assert rows[0]["yieldCiLow"] > 0
    assert rows[0]["significant"] is True


def test_breakdown_does_not_flag_a_large_but_breakeven_sample_as_significant():
    """Lots of bets with no real edge should stay flagged as not significant."""
    # 50 bets, 50% win rate at odds 2.0: expected profit is exactly zero.
    bets = [make_bet(d, won=(d % 2 == 0), odds=2.0) for d in range(1, 51)]

    rows = bs.breakdown_by_market(bets)

    assert rows[0]["bets"] == 50
    assert rows[0]["yieldCiLow"] < 0 < rows[0]["yieldCiHigh"]
    assert rows[0]["significant"] is False


# ----------------------------------------------------------------------
# Temporal stability (walk-forward-style consistency check)
# ----------------------------------------------------------------------
def test_stability_flags_a_market_that_wins_in_both_halves_as_consistent():
    bets = [make_bet(d, won=True, odds=2.0) for d in range(1, 21)]

    rows = bs.temporal_stability(bets)

    assert rows[0]["bets"] == 20
    assert rows[0]["firstHalf"]["yield"] == 100.0
    assert rows[0]["secondHalf"]["yield"] == 100.0
    assert rows[0]["consistent"] is True


def test_stability_flags_a_streak_confined_to_one_half_as_inconsistent():
    """All the wins came early; the second half is pure losses -- the overall
    yield could still look positive, but it is not an ongoing edge."""
    bets = [make_bet(d, won=True, odds=2.0) for d in range(1, 11)] + [
        make_bet(d, won=False, odds=2.0) for d in range(11, 21)
    ]

    rows = bs.temporal_stability(bets)

    assert rows[0]["firstHalf"]["yield"] == 100.0
    assert rows[0]["secondHalf"]["yield"] == -100.0
    assert rows[0]["consistent"] is False


def test_stability_skips_markets_below_the_minimum_sample_per_half():
    bets = [make_bet(d, won=True, odds=2.0) for d in range(1, 15)]  # 14 < 2*10

    rows = bs.temporal_stability(bets)

    assert rows == []


def test_stability_splits_by_date_order_not_insertion_order():
    shuffled = [make_bet(d, won=(d <= 10), odds=2.0) for d in (15, 3, 18, 1, 20, 2)]
    shuffled += [make_bet(d, won=(d <= 10), odds=2.0) for d in range(4, 20) if d not in (15, 18)]

    rows = bs.temporal_stability(shuffled)

    first = rows[0]["firstHalf"]
    second = rows[0]["secondHalf"]
    # Earliest-dated half (days 1-10) all won; latest-dated half (11-20) all lost,
    # regardless of the order bets were passed in.
    assert first["yield"] == 100.0
    assert second["yield"] == -100.0


# ----------------------------------------------------------------------
# Today's slate
# ----------------------------------------------------------------------
def make_open_bet(odds=2.0, probability=0.6, won=None, time="10:00", started=False):
    return bs.OpenBet(
        prediction_id=f"PRED-{time}-{odds}",
        match="A vs B",
        league="Test Open",
        time=time,
        sport="tennis",
        market="Match Winner",
        selection="A",
        odds=odds,
        probability=probability,
        confidence=int(probability * 100),
        won=won,
        started=started,
    )


def test_today_bounds_the_day_between_all_lose_and_all_win():
    plan = StakePlan(strategy="percent", stake_pct=10.0)
    today = bs.plan_today(
        [make_open_bet(odds=2.0, probability=0.6), make_open_bet(odds=3.0, probability=0.4, time="12:00")],
        initial=100.0,
        plan=plan,
    )

    assert today["staked"] == pytest.approx(20.0)
    assert today["best"]["profit"] == pytest.approx(10.0 * 1.0 + 10.0 * 2.0)
    assert today["best"]["final"] == pytest.approx(130.0)
    assert today["worst"]["profit"] == pytest.approx(-20.0)
    # 10*(0.6*2-1) + 10*(0.4*3-1) = 2 + 2
    assert today["expected"]["profit"] == pytest.approx(4.0)


def test_today_scales_stakes_to_the_daily_exposure_limit():
    plan = StakePlan(strategy="percent", stake_pct=10.0, max_stake_pct=10.0)
    today = bs.plan_today([make_open_bet() for _ in range(10)], initial=100.0, plan=plan)

    assert today["exposureCapped"] is True
    assert today["staked"] == pytest.approx(100.0 * bs.MAX_DAILY_EXPOSURE)
    assert today["items"][0]["stake"] == pytest.approx(5.0)


def test_today_kelly_drops_bets_without_edge():
    plan = StakePlan(strategy="kelly", kelly_multiplier=1.0, max_stake_pct=50.0)
    today = bs.plan_today(
        [make_open_bet(odds=2.0, probability=0.6), make_open_bet(odds=2.0, probability=0.4)],
        initial=100.0,
        plan=plan,
    )

    assert today["bets"] == 1
    assert today["skippedNoStake"] == 1


def test_today_tracks_what_already_settled():
    plan = StakePlan(strategy="percent", stake_pct=10.0)
    today = bs.plan_today(
        [make_open_bet(won=True), make_open_bet(won=False, time="11:00"), make_open_bet(time="12:00")],
        initial=100.0,
        plan=plan,
    )

    assert today["pendingBets"] == 1
    assert today["pendingStaked"] == pytest.approx(10.0)
    assert today["realized"]["profit"] == pytest.approx(10.0 - 10.0)


def test_today_without_bets_is_not_an_error():
    today = bs.plan_today([], initial=100.0, plan=StakePlan())

    assert today["bets"] == 0
    assert today["best"]["profit"] == 0.0


def test_min_edge_filter_uses_probability_times_odds():
    assert bs._passes_edge(0.6, 2.0, None) is True
    assert bs._passes_edge(0.6, 2.0, 0.05) is True      # edge +20%
    assert bs._passes_edge(0.64, 1.04, 0.0) is False    # heavy favourite, edge -33%


# ----------------------------------------------------------------------
# Aggressive (all-in) plan
# ----------------------------------------------------------------------
def test_aggressive_picks_the_best_pending_edge_and_states_the_risk():
    plan = bs.aggressive_plan(
        [
            make_open_bet(odds=2.0, probability=0.55),               # edge +10%
            make_open_bet(odds=1.5, probability=0.60, time="11:00"),  # edge -10%
            make_open_bet(odds=3.0, probability=0.90, won=True),      # already played
        ],
        initial=10.0,
        target_multiple=2.0,
    )

    assert plan["note"] is None
    assert plan["pick"]["odds"] == 2.0
    assert plan["allIn"]["finalIfWin"] == pytest.approx(20.0)
    assert plan["allIn"]["probLoseAll"] == pytest.approx(45.0)
    assert plan["chain"]["steps"] == 1


def test_aggressive_chain_needs_consecutive_wins_for_a_bigger_target():
    plan = bs.aggressive_plan(
        [make_open_bet(odds=2.0, probability=0.5)], initial=10.0, target_multiple=8.0
    )

    assert plan["chain"]["steps"] == 3
    assert plan["chain"]["finalIfAllWin"] == pytest.approx(80.0)
    assert plan["chain"]["probAllWin"] == pytest.approx(12.5)


def test_aggressive_flags_a_slate_without_positive_edge():
    plan = bs.aggressive_plan(
        [make_open_bet(odds=1.04, probability=0.64)], initial=10.0, target_multiple=2.0
    )

    assert plan["note"] == "sin_edge_positivo"
    assert plan["positiveEdgeBets"] == 0
    assert plan["pick"]["edge"] < 0


def test_aggressive_without_pending_bets_says_so():
    plan = bs.aggressive_plan([make_open_bet(won=False)], initial=10.0, target_multiple=2.0)

    assert plan["note"] == "sin_apuestas"
    assert plan["pick"] is None


def test_aggressive_never_picks_a_match_already_under_way():
    plan = bs.aggressive_plan(
        [
            make_open_bet(odds=3.0, probability=0.9, started=True),   # best edge, but live
            make_open_bet(odds=2.0, probability=0.55, time="11:00"),
        ],
        initial=10.0,
        target_multiple=2.0,
    )

    assert plan["pendingBets"] == 1
    assert plan["pick"]["odds"] == 2.0


def test_today_counts_bets_on_matches_not_started_yet():
    today = bs.plan_today(
        [make_open_bet(started=True), make_open_bet(time="12:00")],
        initial=100.0,
        plan=StakePlan(strategy="percent", stake_pct=10.0),
    )

    assert today["pendingBets"] == 2
    assert today["notStartedBets"] == 1
