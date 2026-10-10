"""Bankroll ("caja") simulation over validated predictions.

Answers the practical question: if I put X money in and bet the predictions
this platform produces, how does the bankroll evolve and how long would it
take to double it?

Design notes:
- The simulation is a *backtest over real outcomes*: only predictions that
  already have a validated result (win/loss) AND stored decimal odds for the
  chosen selection are used. Odds are read from `reasoning_data.oddsDecimal`
  via the same helper the calibration service uses, so a bet is only counted
  when we know what it would actually have paid.
- Bets are settled in daily rounds: every bet of a given day is staked out of
  the bankroll as it stood at the start of that day (you cannot reinvest the
  profit of a match that has not finished yet). This also makes "days to
  double" a calendar-time answer rather than a per-bet one.
- The projection extrapolates the backtest's geometric daily growth. The
  Monte Carlo resamples the historical bets (bootstrap) to show how wide the
  spread around that single historical path really is.

Nothing here is a promise about the future: with a few dozen bets the spread
is huge, so the response carries the sample size and the UI says so.
"""
import math
import random
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session, joinedload

from src.application.calibration_service import _odds_for_outcome
from src.application.market_anchor_service import anchored_probability, model_probability
from src.application.clv_service import closing_odds_for_prediction, compute_clv
from src.domain.models import (
    Match,
    MatchCompetitor,
    Prediction,
    PredictionResult,
    Sport,
)
from src.timezone import BOGOTA_TZ, today_bogota

# A day never risks more than this share of the bankroll: with many picks on
# the same day a naive per-bet percentage would otherwise stake over 100%.
MAX_DAILY_EXPOSURE = 0.5
# Below this multiple of the initial bankroll the caja is considered busted.
RUIN_MULTIPLE = 0.1

# Markets paused as betting recommendations while under review/redesign.
# "Exact Set Score" showed a statistically significant loss (z-test, 95% CI
# entirely below zero) that got WORSE in the second half of its history, not
# better (see temporal_stability) -- the opposite of what you'd see from a
# market that just needs more data. Paused here on 2026-10-02 pending a
# redesign of how the engine prices 6-way exact-score markets.
# Mirrored in the frontend as PAUSED_BETTING_MARKETS (frontend/src/views/
# Dashboard.vue) and isPausedMarket (PredictionDetail.vue) -- update both
# sides together. Predictions keep being generated and validated for this
# market (so there is data to judge the eventual redesign against); this
# only excludes it from the DEFAULT betting universe. Passing `market=` for
# a paused market explicitly still works, for monitoring/comparison.
PAUSED_BETTING_MARKETS = {"Exact Set Score"}

STRATEGIES = ("percent", "flat", "kelly")


@dataclass(frozen=True)
class Bet:
    """One settled bet: what it paid, whether it won, and what we believed."""

    day: date
    sport: str
    market: str
    odds: float
    won: bool
    probability: float
    confidence: int
    expected_value: Optional[float] = None
    closing_odds: Optional[float] = None
    clv: Optional[float] = None


@dataclass(frozen=True)
class StakePlan:
    """How much of the bankroll goes into each bet."""

    strategy: str = "percent"
    stake_pct: float = 2.0          # % of current bankroll (percent) or of the initial (flat)
    kelly_multiplier: float = 0.5   # fractional Kelly
    max_stake_pct: float = 10.0     # hard cap per bet, any strategy

    def normalized(self) -> "StakePlan":
        strategy = self.strategy if self.strategy in STRATEGIES else "percent"
        return replace(
            self,
            strategy=strategy,
            stake_pct=max(0.1, min(50.0, float(self.stake_pct))),
            kelly_multiplier=max(0.05, min(1.0, float(self.kelly_multiplier))),
            max_stake_pct=max(0.1, min(50.0, float(self.max_stake_pct))),
        )


def _kelly_fraction(prob: float, odds: float) -> float:
    b = odds - 1.0
    if b <= 0:
        return 0.0
    return max(0.0, (b * prob - (1.0 - prob)) / b)


def _stake_for(bet: Bet, bankroll: float, initial: float, plan: StakePlan) -> float:
    """Stake for one bet, before the daily-exposure scaling."""
    cap = bankroll * plan.max_stake_pct / 100.0
    if plan.strategy == "flat":
        stake = initial * plan.stake_pct / 100.0
    elif plan.strategy == "kelly":
        stake = bankroll * _kelly_fraction(bet.probability, bet.odds) * plan.kelly_multiplier
    else:  # percent
        stake = bankroll * plan.stake_pct / 100.0
    return max(0.0, min(stake, cap, bankroll))


def _settle_day(
    day_bets: Sequence[Bet], bankroll: float, initial: float, plan: StakePlan
) -> Tuple[float, float]:
    """Return (staked, profit) for one day of bets, all funded at day start."""
    stakes = [_stake_for(b, bankroll, initial, plan) for b in day_bets]
    total = sum(stakes)
    limit = bankroll * MAX_DAILY_EXPOSURE
    if total > limit and total > 0:
        scale = limit / total
        stakes = [s * scale for s in stakes]
        total = limit
    profit = sum(
        s * (b.odds - 1.0) if b.won else -s
        for s, b in zip(stakes, day_bets)
    )
    return total, profit


def _group_by_day(bets: Sequence[Bet]) -> List[Tuple[date, List[Bet]]]:
    grouped: Dict[date, List[Bet]] = {}
    for bet in bets:
        grouped.setdefault(bet.day, []).append(bet)
    return sorted(grouped.items())


def simulate_bankroll(
    bets: Sequence[Bet], initial: float, plan: StakePlan
) -> Dict[str, Any]:
    """Walk the real bet history day by day and return the bankroll curve."""
    plan = plan.normalized()
    bankroll = float(initial)
    peak = bankroll
    max_drawdown = 0.0
    staked_total = 0.0
    curve: List[Dict[str, Any]] = []
    settled = 0
    busted = False

    for day, day_bets in _group_by_day(bets):
        staked, profit = _settle_day(day_bets, bankroll, initial, plan)
        bankroll += profit
        staked_total += staked
        settled += len(day_bets)
        peak = max(peak, bankroll)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - bankroll) / peak)
        curve.append(
            {
                "date": day.isoformat(),
                "bets": len(day_bets),
                "staked": round(staked, 2),
                "profit": round(profit, 2),
                "bankroll": round(bankroll, 2),
            }
        )
        if bankroll <= initial * RUIN_MULTIPLE:
            busted = True
            break

    wins = sum(1 for b in bets if b.won)
    avg_odds = sum(b.odds for b in bets) / len(bets) if bets else None
    profit_total = bankroll - initial
    days_span = 0
    if curve:
        first = date.fromisoformat(curve[0]["date"])
        last = date.fromisoformat(curve[-1]["date"])
        days_span = (last - first).days + 1

    daily_growth = None
    if days_span > 0 and bankroll > 0 and initial > 0:
        daily_growth = (bankroll / initial) ** (1.0 / days_span)

    return {
        "initial": round(float(initial), 2),
        "final": round(bankroll, 2),
        "profit": round(profit_total, 2),
        "staked": round(staked_total, 2),
        "roi": round(profit_total / initial * 100, 2) if initial else None,
        "yield": round(profit_total / staked_total * 100, 2) if staked_total else None,
        "multiple": round(bankroll / initial, 3) if initial else None,
        "bets": len(bets),
        "settledBets": settled,
        "wins": wins,
        "losses": len(bets) - wins,
        "winRate": round(wins / len(bets) * 100, 2) if bets else None,
        "avgOdds": round(avg_odds, 3) if avg_odds else None,
        "maxDrawdown": round(max_drawdown * 100, 2),
        "daysSpan": days_span,
        "activeDays": len(curve),
        "betsPerDay": round(len(bets) / days_span, 2) if days_span else None,
        "dailyGrowth": round(daily_growth, 6) if daily_growth else None,
        "busted": busted,
        "curve": curve,
    }


def project_to_target(
    backtest: Dict[str, Any], target_multiple: float, horizon_days: int = 1825
) -> Dict[str, Any]:
    """Extrapolate the backtest's daily growth until the bankroll multiplies."""
    target_multiple = max(1.01, float(target_multiple))
    growth = backtest.get("dailyGrowth")
    target_amount = round(backtest["initial"] * target_multiple, 2)
    out: Dict[str, Any] = {
        "targetMultiple": target_multiple,
        "targetAmount": target_amount,
        "dailyGrowthPct": round((growth - 1.0) * 100, 3) if growth else None,
        "daysToTarget": None,
        "betsToTarget": None,
        "etaDate": None,
        "reachable": False,
        "note": None,
    }

    if backtest["bets"] == 0:
        out["note"] = "sin_datos"
        return out
    if backtest["multiple"] and backtest["multiple"] >= target_multiple:
        out["reachable"] = True
        out["daysToTarget"] = 0
        out["note"] = "ya_alcanzado"
        return out
    if not growth or growth <= 1.0:
        out["note"] = "sin_ventaja"  # historical edge is zero or negative
        return out

    days = math.log(target_multiple) / math.log(growth)
    if days > horizon_days:
        out["note"] = "horizonte_excedido"
        return out

    bets_per_day = backtest.get("betsPerDay") or 0
    out["reachable"] = True
    out["daysToTarget"] = round(days, 1)
    out["betsToTarget"] = int(round(days * bets_per_day)) if bets_per_day else None
    out["etaDate"] = (today_bogota() + timedelta(days=math.ceil(days))).isoformat()
    return out


def monte_carlo(
    bets: Sequence[Bet],
    initial: float,
    plan: StakePlan,
    target_multiple: float,
    bets_per_day: float,
    sims: int = 400,
    horizon_days: int = 365,
    seed: int = 20260101,
) -> Dict[str, Any]:
    """Bootstrap the historical bets to bound how long doubling could take.

    Each simulated day draws `bets_per_day` bets at random (with replacement)
    from the real history and settles them with the same staking rules. The
    spread of the finishing days is the honest version of "how long it takes":
    one historical path is not a forecast.
    """
    if not bets or bets_per_day <= 0 or initial <= 0:
        return {"sims": 0, "note": "sin_datos"}

    plan = plan.normalized()
    rng = random.Random(seed)
    target_amount = initial * max(1.01, float(target_multiple))
    ruin_amount = initial * RUIN_MULTIPLE
    whole_f, frac = divmod(float(bets_per_day), 1.0)
    whole = int(whole_f)

    reached_days: List[float] = []
    finals: List[float] = []
    ruined = 0

    for _ in range(sims):
        bankroll = float(initial)
        for day in range(1, horizon_days + 1):
            k = whole + (1 if rng.random() < frac else 0)
            if k:
                day_bets = [bets[rng.randrange(len(bets))] for _ in range(k)]
                _, profit = _settle_day(day_bets, bankroll, initial, plan)
                bankroll += profit
            if bankroll >= target_amount:
                reached_days.append(float(day))
                break
            if bankroll <= ruin_amount:
                ruined += 1
                break
        finals.append(bankroll)

    reached_days.sort()
    finals.sort()

    def _pct(values: List[float], q: float) -> Optional[float]:
        if not values:
            return None
        idx = min(len(values) - 1, max(0, int(round(q * (len(values) - 1)))))
        return values[idx]

    def _days_pct(q: float) -> Optional[float]:
        # Over ALL scenarios: one that never gets there counts as "never",
        # so the median only exists when at least half of them arrive.
        idx = min(sims - 1, max(0, int(round(q * (sims - 1)))))
        return reached_days[idx] if idx < len(reached_days) else None

    return {
        "sims": sims,
        "horizonDays": horizon_days,
        "betsPerDay": round(bets_per_day, 2),
        "probReachTarget": round(len(reached_days) / sims * 100, 1),
        "probRuin": round(ruined / sims * 100, 1),
        "daysP10": _days_pct(0.10),
        "daysP50": _days_pct(0.50),
        "daysP90": _days_pct(0.90),
        # Only among the scenarios that did arrive -- survivorship-biased on
        # its own, always read it next to probReachTarget.
        "daysP50IfReached": _pct(reached_days, 0.50),
        "finalP10": round(_pct(finals, 0.10) or 0.0, 2),
        "finalP50": round(_pct(finals, 0.50) or 0.0, 2),
        "finalP90": round(_pct(finals, 0.90) or 0.0, 2),
    }


MIN_SAMPLE_FOR_SIGNIFICANCE = 30


def _flat_yield_stats(bets: Sequence[Bet]) -> Dict[str, Any]:
    """Mean per-bet profit at flat 1-unit stakes, its 95% CI and whether it
    is distinguishable from zero edge (same test as `breakdown_by_market`)."""
    n = len(bets)
    if n == 0:
        return {"bets": 0, "yield": None, "yieldCiLow": None, "yieldCiHigh": None, "significant": False}
    profits = [(b.odds - 1.0) if b.won else -1.0 for b in bets]
    mean_profit = sum(profits) / n
    se = 0.0
    if n > 1:
        variance = sum((p - mean_profit) ** 2 for p in profits) / (n - 1)
        se = math.sqrt(variance / n)
    ci_low = mean_profit - 1.96 * se
    ci_high = mean_profit + 1.96 * se
    return {
        "bets": n,
        "yield": round(mean_profit * 100, 2),
        "yieldCiLow": round(ci_low * 100, 2),
        "yieldCiHigh": round(ci_high * 100, 2),
        "significant": n >= MIN_SAMPLE_FOR_SIGNIFICANCE and (ci_low > 0 or ci_high < 0),
    }


def build_verdict(
    bets: Sequence[Bet],
    backtest: Dict[str, Any],
    projection: Dict[str, Any],
    mc: Dict[str, Any],
) -> Dict[str, Any]:
    """One answer out of three signals that can disagree.

    The projection extrapolates a single historical path, the Monte Carlo
    resamples it, and the significance test says whether the yield behind
    both is more than noise. A growing backtest is only called a real edge
    when the yield is significant AND most resampled scenarios get there;
    otherwise the headline must not promise a number of days.

    Levels: sin_datos, pierde, ya_alcanzado, edge_real, no_concluyente.
    """
    edge = _flat_yield_stats(bets)
    out: Dict[str, Any] = {
        "level": "no_concluyente",
        "edge": edge,
        "probReachTarget": mc.get("probReachTarget"),
        "probRuin": mc.get("probRuin"),
        "horizonDays": mc.get("horizonDays"),
        "typicalDays": mc.get("daysP50"),
        "projectedDays": projection.get("daysToTarget"),
        "reasons": [],
    }
    note = projection.get("note")
    if note == "sin_datos":
        out["level"] = "sin_datos"
        return out
    if note == "sin_ventaja":
        out["level"] = "pierde"
        return out

    reasons: List[str] = []
    if edge["bets"] < MIN_SAMPLE_FOR_SIGNIFICANCE:
        reasons.append("muestra_chica")
    elif not edge["significant"]:
        reasons.append("yield_no_significativo")
    if mc.get("sims") and (mc.get("probReachTarget") or 0.0) < 50.0:
        reasons.append("mayoria_no_llega")
    if mc.get("sims") and (mc.get("probRuin") or 0.0) > 20.0:
        reasons.append("riesgo_quiebra")
    if note == "horizonte_excedido":
        reasons.append("demasiado_lento")
    out["reasons"] = reasons

    if not reasons:
        out["level"] = "ya_alcanzado" if note == "ya_alcanzado" else "edge_real"
    return out


def caja_by_market(
    bets: Sequence[Bet],
    initial: float,
    plan: StakePlan,
    target_multiple: float,
    sims: int = 400,
    horizon_days: int = 365,
) -> List[Dict[str, Any]]:
    """The whole caja answer once per market, side by side.

    Each row is exactly what `simulate` would say if the caller filtered to
    that market (same backtest, projection, Monte Carlo and verdict), plus a
    leading row for the default betting universe (every non-paused market
    together), so the markets can be compared without re-running the filter.
    `bets` must include paused markets; they come back flagged `paused`.
    """

    def _row(sport: Optional[str], market: Optional[str], items: Sequence[Bet]) -> Dict[str, Any]:
        backtest = simulate_bankroll(items, initial, plan)
        projection = project_to_target(backtest, target_multiple)
        mc = monte_carlo(
            items,
            initial,
            plan,
            target_multiple,
            bets_per_day=backtest.get("betsPerDay") or 0,
            sims=sims,
            horizon_days=horizon_days,
        )
        verdict = build_verdict(items, backtest, projection, mc)
        return {
            "sport": sport,
            "market": market,
            "paused": market in PAUSED_BETTING_MARKETS,
            "bets": backtest["bets"],
            "final": backtest["final"],
            "profit": backtest["profit"],
            "yield": backtest["yield"],
            "winRate": backtest["winRate"],
            "avgOdds": backtest["avgOdds"],
            "maxDrawdown": backtest["maxDrawdown"],
            "daysToTarget": projection["daysToTarget"],
            "probReachTarget": mc.get("probReachTarget"),
            "probRuin": mc.get("probRuin"),
            "level": verdict["level"],
            "reasons": verdict["reasons"],
        }

    groups: Dict[Tuple[str, str], List[Bet]] = {}
    for bet in bets:
        groups.setdefault((bet.sport, bet.market), []).append(bet)

    rows = [_row(sport, market, items) for (sport, market), items in groups.items()]
    rows.sort(key=lambda r: (r["paused"], -(r["final"] or 0.0)))

    active = [b for b in bets if b.market not in PAUSED_BETTING_MARKETS]
    if active:
        rows.insert(0, _row(None, None, active))
    return rows


def breakdown_by_market(bets: Sequence[Bet]) -> List[Dict[str, Any]]:
    """Flat 1-unit yield per (sport, market), with a significance check.

    `yield` alone can't tell a real edge from noise at the sample sizes this
    platform has so far. Testing several markets and keeping only the one that
    "worked" is the classic multiple-comparisons trap: if NONE of them had any
    real edge, you'd still expect one or two to look profitable just by chance.
    `significant` is a two-sided z-test on the mean per-bet profit (flat 1-unit
    stakes) against the null hypothesis of zero edge — it only turns true when
    there are at least `MIN_SAMPLE_FOR_SIGNIFICANCE` bets AND the 95% CI of
    that mean excludes zero. When it's false, treat the yield as noise, not a
    discovered strategy, no matter how good it looks.
    """
    groups: Dict[Tuple[str, str], List[Bet]] = {}
    for bet in bets:
        groups.setdefault((bet.sport, bet.market), []).append(bet)

    rows = []
    for (sport, market), items in groups.items():
        n = len(items)
        wins = sum(1 for b in items if b.won)
        profits = [(b.odds - 1.0) if b.won else -1.0 for b in items]
        profit = sum(profits)
        mean_profit = profit / n

        se = 0.0
        if n > 1:
            variance = sum((p - mean_profit) ** 2 for p in profits) / (n - 1)
            se = math.sqrt(variance / n)
        ci_low = mean_profit - 1.96 * se
        ci_high = mean_profit + 1.96 * se
        significant = n >= MIN_SAMPLE_FOR_SIGNIFICANCE and (ci_low > 0 or ci_high < 0)

        clv_values = [b.clv for b in items if b.clv is not None]
        avg_clv = sum(clv_values) / len(clv_values) if clv_values else None
        positive_clv = sum(1 for c in clv_values if c > 0)

        rows.append(
            {
                "sport": sport,
                "market": market,
                "bets": n,
                "wins": wins,
                "winRate": round(wins / n * 100, 1),
                "avgOdds": round(sum(b.odds for b in items) / n, 3),
                "profitUnits": round(profit, 2),
                "yield": round(mean_profit * 100, 2),
                "yieldCiLow": round(ci_low * 100, 2),
                "yieldCiHigh": round(ci_high * 100, 2),
                "significant": significant,
                "clvSamples": len(clv_values),
                "avgClv": round(avg_clv * 100, 2) if avg_clv is not None else None,
                "positiveClvPct": round(positive_clv / len(clv_values) * 100, 1) if clv_values else None,
            }
        )
    rows.sort(key=lambda r: r["profitUnits"], reverse=True)
    return rows


MIN_SAMPLE_PER_HALF = 10


def temporal_stability(bets: Sequence[Bet]) -> List[Dict[str, Any]]:
    """Split each market's history in half by date and report the yield in
    each half separately.

    This is the walk-forward check that actually matters for this codebase:
    calibration curves and ensemble weights are refit on ALL validated
    outcomes seen so far (including the ones a backtest then grades), but
    that look-ahead bias turns out not to move `yield` here at all for the
    `percent`/`flat` strategies, because they size every bet the same
    regardless of probability (only `kelly` staking even reads calibrated
    probability, and nothing here filters WHICH bets to place by edge). What
    a flat-stake yield number can't tell you on its own is whether an edge is
    a standing property of the market or a one-off streak that already
    happened: testing several markets and keeping the one with the best
    overall yield is exactly how a streak confined to a few lucky weeks gets
    mistaken for a real, ongoing edge (see `breakdown_by_market`'s
    significance test for the matching problem on sample size). A market
    whose yield is positive in BOTH the earlier and the later half of its
    history is far more likely to reflect something real and ongoing than
    one whose overall yield is carried entirely by one half.
    """
    groups: Dict[Tuple[str, str], List[Bet]] = {}
    for bet in bets:
        groups.setdefault((bet.sport, bet.market), []).append(bet)

    def _half_yield(items: Sequence[Bet]) -> Optional[float]:
        if not items:
            return None
        profit = sum((b.odds - 1.0) if b.won else -1.0 for b in items)
        return round(profit / len(items) * 100, 2)

    rows = []
    for (sport, market), items in groups.items():
        items = sorted(items, key=lambda b: b.day)
        n = len(items)
        if n < 2 * MIN_SAMPLE_PER_HALF:
            continue
        mid = n // 2
        first, second = items[:mid], items[mid:]
        first_yield = _half_yield(first)
        second_yield = _half_yield(second)
        rows.append(
            {
                "sport": sport,
                "market": market,
                "bets": n,
                "firstHalf": {
                    "bets": len(first),
                    "from": first[0].day.isoformat(),
                    "to": first[-1].day.isoformat(),
                    "yield": first_yield,
                },
                "secondHalf": {
                    "bets": len(second),
                    "from": second[0].day.isoformat(),
                    "to": second[-1].day.isoformat(),
                    "yield": second_yield,
                },
                "consistent": first_yield is not None and second_yield is not None
                and first_yield > 0 and second_yield > 0,
            }
        )
    rows.sort(key=lambda r: r["bets"], reverse=True)
    return rows


# ----------------------------------------------------------------------
# Today's slate: what the initial amount could make with today's bets
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class OpenBet:
    """One of today's predictions with a known price (settled or not yet)."""

    prediction_id: str
    match: str
    league: Optional[str]
    time: Optional[str]
    sport: str
    market: str
    selection: str
    odds: float
    probability: float
    confidence: int
    won: Optional[bool] = None  # None while the match has not been validated
    started: bool = False       # kick-off time passed (or match no longer SCHEDULED)
    model_probability: Optional[float] = None  # the model alone, before anchoring


# An edge this large has historically been the model disagreeing with a
# market that was right (20-50% promised, -24% realized on 2026-10-10).
SUSPICIOUS_EDGE = 0.20


def _bet_probability(
    sport: str,
    market: str,
    confidence: int,
    reasoning_data: Optional[Dict[str, Any]],
    odds: float,
    odds_markets: Optional[Dict[str, Any]],
    use_calibrated: bool,
) -> Tuple[float, float]:
    """(probability to stake on, the model's own probability).

    The first is anchored to the bookmaker's price (see
    `market_anchor_service`); with `use_calibrated=False` both are the raw
    model confidence, for comparing against the untouched model.
    """
    raw = confidence / 100.0
    if not use_calibrated:
        return raw, raw
    anchored = anchored_probability(sport, market, confidence, reasoning_data, odds, odds_markets)
    if anchored:
        return anchored["probability"], anchored["modelProbability"]
    model = model_probability(sport, market, confidence)
    return (model if model is not None else raw,) * 2


def _passes_edge(probability: float, odds: float, min_edge: Optional[float]) -> bool:
    """Edge = p * odds - 1 with the probability the simulation stakes on
    (market-anchored when available), the same number the UI shows per bet."""
    return min_edge is None or probability * odds - 1.0 >= min_edge


def plan_today(
    open_bets: Sequence[OpenBet], initial: float, plan: StakePlan
) -> Dict[str, Any]:
    """Stake today's bets out of `initial` and bound what the day can return.

    Same rules as one day of the backtest (`_settle_day`): every bet is funded
    from the bankroll at the start of the day and the total is scaled down to
    `MAX_DAILY_EXPOSURE`. `best` is every bet winning, `worst` every bet
    losing, `expected` weighs each bet by its (calibrated) probability.
    """
    plan = plan.normalized()
    initial = float(initial)
    stakes = [_stake_for(b, initial, initial, plan) for b in open_bets]
    total = sum(stakes)
    limit = initial * MAX_DAILY_EXPOSURE
    scaled = total > limit and total > 0
    if scaled:
        stakes = [s * limit / total for s in stakes]

    rows = []
    best = expected = realized = 0.0
    staked = pending_staked = 0.0
    for stake, bet in zip(stakes, open_bets):
        if stake <= 0:
            continue  # kelly with no edge: not a bet
        win_profit = stake * (bet.odds - 1.0)
        exp_profit = stake * (bet.probability * bet.odds - 1.0)
        staked += stake
        best += win_profit
        expected += exp_profit
        if bet.won is None:
            pending_staked += stake
        else:
            realized += win_profit if bet.won else -stake
        rows.append(
            {
                "predictionId": bet.prediction_id,
                "match": bet.match,
                "league": bet.league,
                "time": bet.time,
                "sport": bet.sport,
                "market": bet.market,
                "selection": bet.selection,
                "odds": round(bet.odds, 3),
                "probability": round(bet.probability * 100, 1),
                "edge": round((bet.probability * bet.odds - 1.0) * 100, 1),
                "modelEdge": (
                    round((bet.model_probability * bet.odds - 1.0) * 100, 1)
                    if bet.model_probability is not None
                    else None
                ),
                "suspicious": (
                    bet.model_probability is not None
                    and bet.model_probability * bet.odds - 1.0 > SUSPICIOUS_EDGE
                ),
                "stake": round(stake, 2),
                "winProfit": round(win_profit, 2),
                "expectedProfit": round(exp_profit, 2),
                "won": bet.won,
                "started": bet.started,
            }
        )
    rows.sort(key=lambda r: (r["time"] or "", r["match"]))

    def _outcome(profit: float) -> Dict[str, Any]:
        return {
            "profit": round(profit, 2),
            "final": round(initial + profit, 2),
            "pct": round(profit / initial * 100, 2) if initial else None,
        }

    return {
        "date": today_bogota().isoformat(),
        "bets": len(rows),
        "skippedNoStake": len(open_bets) - len(rows),
        "pendingBets": sum(1 for r in rows if r["won"] is None),
        "notStartedBets": sum(1 for r in rows if r["won"] is None and not r["started"]),
        "staked": round(staked, 2),
        "stakedPct": round(staked / initial * 100, 2) if initial else None,
        "exposureCapped": scaled,
        "best": _outcome(best),
        "expected": _outcome(expected),
        "worst": _outcome(-staked),
        "realized": _outcome(realized),
        "pendingStaked": round(pending_staked, 2),
        "items": rows,
    }


def aggressive_plan(
    open_bets: Sequence[OpenBet], initial: float, target_multiple: float
) -> Dict[str, Any]:
    """All-in on today's single best bet: the honest version of "double it
    in a day".

    Picks the not-yet-played bet with the highest edge and reports what
    staking the WHOLE amount on it means: the payout if it wins and the
    probability of losing everything if it does not. For a target above one
    bet's odds it also reports the chain: how many consecutive all-in wins on
    bets like this one are needed (one per day) and the probability of
    stringing them together. Ignores the staking plan and the daily exposure
    cap on purpose -- that is what "aggressive" means here.
    """
    initial = float(initial)
    target_multiple = max(1.01, float(target_multiple))
    # Only matches that have not started: you cannot go all-in on a live one.
    pending = [b for b in open_bets if b.won is None and not b.started and b.odds > 1.0]

    def _edge(b: OpenBet) -> float:
        return b.probability * b.odds - 1.0

    out: Dict[str, Any] = {
        "targetMultiple": target_multiple,
        "pendingBets": len(pending),
        "positiveEdgeBets": sum(1 for b in pending if _edge(b) > 0),
        "pick": None,
        "note": None,
    }
    if not pending:
        out["note"] = "sin_apuestas"
        return out

    best = max(pending, key=_edge)
    edge = _edge(best)
    if edge <= 0:
        out["note"] = "sin_edge_positivo"

    p = min(max(best.probability, 0.0), 1.0)
    steps = max(1, math.ceil(math.log(target_multiple) / math.log(best.odds) - 1e-9))
    out["pick"] = {
        "predictionId": best.prediction_id,
        "match": best.match,
        "league": best.league,
        "time": best.time,
        "sport": best.sport,
        "market": best.market,
        "selection": best.selection,
        "odds": round(best.odds, 3),
        "probability": round(p * 100, 1),
        "edge": round(edge * 100, 1),
        "modelEdge": (
            round((best.model_probability * best.odds - 1.0) * 100, 1)
            if best.model_probability is not None
            else None
        ),
        "kellyPct": round(_kelly_fraction(p, best.odds) * 100, 1),
    }
    out["allIn"] = {
        "stake": round(initial, 2),
        "finalIfWin": round(initial * best.odds, 2),
        "multipleIfWin": round(best.odds, 3),
        "probWin": round(p * 100, 1),
        "probLoseAll": round((1.0 - p) * 100, 1),
    }
    out["chain"] = {
        "steps": steps,
        "days": steps,
        "finalIfAllWin": round(initial * best.odds ** steps, 2),
        "multipleIfAllWin": round(best.odds ** steps, 2),
        "probAllWin": round(p ** steps * 100, 1),
        "probLoseAll": round((1.0 - p ** steps) * 100, 1),
    }
    return out


def load_today_bets(
    db: Session,
    sport: Optional[str] = None,
    market: Optional[str] = None,
    min_confidence: int = 0,
    min_ev: Optional[float] = None,
    use_calibrated: bool = True,
    min_edge: Optional[float] = None,
) -> Tuple[List[OpenBet], int]:
    """Today's (Bogota) predictions with stored odds, plus how many lack odds."""
    start = datetime.combine(today_bogota(), datetime.min.time(), tzinfo=BOGOTA_TZ)
    query = (
        db.query(Prediction, PredictionResult, Match, Sport)
        .outerjoin(PredictionResult, PredictionResult.prediction_id == Prediction.id)
        .join(Match, Match.id == Prediction.match_id)
        .join(Sport, Sport.id == Match.sport_id)
        .options(
            joinedload(Prediction.match)
            .joinedload(Match.competitors)
            .joinedload(MatchCompetitor.competitor),
            joinedload(Prediction.match).joinedload(Match.league),
        )
        .filter(Match.match_date >= start, Match.match_date < start + timedelta(days=1))
        .filter(Match.status.notin_(("CANCELLED", "POSTPONED", "ABANDONED")))
        .filter(Prediction.status != "CANCELLED")
    )
    if sport:
        query = query.filter(Sport.code == sport)
    if market:
        query = query.filter(Prediction.market == market)
    else:
        query = query.filter(~Prediction.market.in_(PAUSED_BETTING_MARKETS))
    if min_confidence:
        query = query.filter(Prediction.confidence >= min_confidence)
    if min_ev is not None:
        query = query.filter(Prediction.expected_value >= min_ev)

    open_bets: List[OpenBet] = []
    without_odds = 0
    now = datetime.now(BOGOTA_TZ)
    for prediction, result, match, sport_row in query.order_by(Match.match_date.asc()).all():
        if prediction.created_at and prediction.created_at >= match.match_date:
            continue  # written after kick-off: never a placeable bet
        home_name = away_name = None
        for mc in match.competitors:
            name = mc.competitor.name if mc.competitor else None
            if mc.side in ("home", "player1"):
                home_name = name
            elif mc.side in ("away", "player2"):
                away_name = name

        odds = _odds_for_outcome(
            prediction.reasoning_data, prediction.predicted_outcome, home_name, away_name
        )
        if not odds:
            without_odds += 1
            continue

        confidence = int(prediction.confidence or 0)
        probability, model_prob = _bet_probability(
            sport_row.code,
            prediction.market,
            confidence,
            prediction.reasoning_data,
            odds,
            (match.extra_data or {}).get("odds_markets"),
            use_calibrated,
        )

        if not _passes_edge(probability, odds, min_edge):
            continue

        won = None
        if result is not None and result.is_successful is not None:
            won = bool(result.is_successful)

        open_bets.append(
            OpenBet(
                prediction_id=prediction.id,
                match=f"{home_name or '?'} vs {away_name or '?'}",
                league=match.league.name if match.league else None,
                time=match.match_date.astimezone(BOGOTA_TZ).strftime("%H:%M"),
                sport=sport_row.code,
                market=prediction.market,
                selection=prediction.predicted_outcome,
                odds=odds,
                probability=probability,
                confidence=confidence,
                won=won,
                started=match.status != "SCHEDULED" or match.match_date <= now,
                model_probability=model_prob,
            )
        )
    return open_bets, without_odds


# ----------------------------------------------------------------------
# Loading real bets from the database
# ----------------------------------------------------------------------
def load_bets(
    db: Session,
    days: int = 180,
    sport: Optional[str] = None,
    market: Optional[str] = None,
    min_confidence: int = 0,
    min_ev: Optional[float] = None,
    use_calibrated: bool = True,
    min_edge: Optional[float] = None,
    include_paused: bool = False,
) -> Tuple[List[Bet], Dict[str, Any]]:
    """Settled predictions with known odds, oldest first, plus sample stats."""
    query = (
        db.query(Prediction, PredictionResult, Match, Sport)
        .join(PredictionResult, PredictionResult.prediction_id == Prediction.id)
        .join(Match, Match.id == Prediction.match_id)
        .join(Sport, Sport.id == Match.sport_id)
        .options(
            joinedload(Prediction.match)
            .joinedload(Match.competitors)
            .joinedload(MatchCompetitor.competitor)
        )
        .filter(PredictionResult.is_successful.isnot(None))
    )
    if days:
        cutoff = datetime.now(BOGOTA_TZ) - timedelta(days=days)
        query = query.filter(Match.match_date >= cutoff)
    if sport:
        query = query.filter(Sport.code == sport)
    if market:
        query = query.filter(Prediction.market == market)
    elif not include_paused:
        # No explicit market filter: default to the betting universe, which
        # excludes paused markets (see PAUSED_BETTING_MARKETS). An explicit
        # `market=` for a paused one still works, for monitoring.
        query = query.filter(~Prediction.market.in_(PAUSED_BETTING_MARKETS))
    if min_confidence:
        query = query.filter(Prediction.confidence >= min_confidence)
    if min_ev is not None:
        query = query.filter(Prediction.expected_value >= min_ev)

    # Prediction.id breaks ties: the Monte Carlo resamples by position, so two
    # loads of the same bets must come back in the same order.
    rows = query.order_by(Match.match_date.asc(), Prediction.id.asc()).all()

    bets: List[Bet] = []
    without_odds = 0
    below_edge = 0
    after_start = 0
    for prediction, result, match, sport_row in rows:
        # A prediction written after the match started was never a placeable
        # bet (in-play/final odds, features that may contain the result).
        # 38% of the history up to 2026-10-10 was like this and it carried
        # ALL of the apparent positive yield.
        if prediction.created_at and prediction.created_at >= match.match_date:
            after_start += 1
            continue
        home_name = away_name = None
        for mc in match.competitors:
            name = mc.competitor.name if mc.competitor else None
            if mc.side in ("home", "player1"):
                home_name = name
            elif mc.side in ("away", "player2"):
                away_name = name

        odds = _odds_for_outcome(
            prediction.reasoning_data,
            prediction.predicted_outcome,
            home_name,
            away_name,
        )
        if not odds:
            without_odds += 1
            continue

        confidence = int(prediction.confidence or 0)
        probability, _model_prob = _bet_probability(
            sport_row.code,
            prediction.market,
            confidence,
            prediction.reasoning_data,
            odds,
            (match.extra_data or {}).get("odds_markets"),
            use_calibrated,
        )

        if not _passes_edge(probability, odds, min_edge):
            below_edge += 1
            continue

        closing_odds = None
        if sport_row.code == "tennis":
            closing_odds = closing_odds_for_prediction(
                (match.extra_data or {}).get("odds_markets_closing"),
                prediction.market,
                prediction.predicted_outcome,
                home_name,
                away_name,
                prediction.reasoning_data,
            )

        bets.append(
            Bet(
                day=match.match_date.astimezone(BOGOTA_TZ).date(),
                sport=sport_row.code,
                market=prediction.market,
                odds=odds,
                won=bool(result.is_successful),
                probability=probability,
                confidence=confidence,
                expected_value=(
                    float(prediction.expected_value)
                    if prediction.expected_value is not None
                    else None
                ),
                closing_odds=closing_odds,
                clv=compute_clv(odds, closing_odds),
            )
        )

    sample = {
        "settledPredictions": len(rows),
        "withOdds": len(bets),
        "withoutOdds": without_odds,
        "belowMinEdge": below_edge,
        "afterStart": after_start,
        "oddsCoverage": (
            round((len(bets) + below_edge) / (len(rows) - after_start) * 100, 1)
            if len(rows) > after_start
            else None
        ),
        "firstDate": bets[0].day.isoformat() if bets else None,
        "lastDate": bets[-1].day.isoformat() if bets else None,
    }
    return bets, sample


def simulate(
    db: Session,
    initial: float = 100.0,
    strategy: str = "percent",
    stake_pct: float = 2.0,
    kelly_multiplier: float = 0.5,
    max_stake_pct: float = 10.0,
    target_multiple: float = 2.0,
    days: int = 180,
    sport: Optional[str] = None,
    market: Optional[str] = None,
    min_confidence: int = 0,
    min_ev: Optional[float] = None,
    use_calibrated: bool = True,
    sims: int = 400,
    horizon_days: int = 365,
    min_edge: Optional[float] = None,
) -> Dict[str, Any]:
    """Full caja answer: backtest + projection + Monte Carlo + per-market."""
    plan = StakePlan(
        strategy=strategy,
        stake_pct=stake_pct,
        kelly_multiplier=kelly_multiplier,
        max_stake_pct=max_stake_pct,
    ).normalized()

    bets, sample = load_bets(
        db,
        days=days,
        sport=sport,
        market=market,
        min_confidence=min_confidence,
        min_ev=min_ev,
        use_calibrated=use_calibrated,
        min_edge=min_edge,
    )

    backtest = simulate_bankroll(bets, initial, plan)
    projection = project_to_target(backtest, target_multiple)
    mc = monte_carlo(
        bets,
        initial,
        plan,
        target_multiple,
        bets_per_day=backtest.get("betsPerDay") or 0,
        sims=sims,
        horizon_days=horizon_days,
    )

    # Every market at once (paused ones included, flagged) under the same
    # non-market filters, for the side-by-side comparison.
    all_market_bets, _ = load_bets(
        db,
        days=days,
        sport=sport,
        min_confidence=min_confidence,
        min_ev=min_ev,
        use_calibrated=use_calibrated,
        min_edge=min_edge,
        include_paused=True,
    )

    # Loaded without the edge filter: the aggressive block needs the whole
    # slate to say "nothing has positive edge today" instead of going blank.
    today_all, today_without_odds = load_today_bets(
        db,
        sport=sport,
        market=market,
        min_confidence=min_confidence,
        min_ev=min_ev,
        use_calibrated=use_calibrated,
    )
    today = plan_today(
        [b for b in today_all if _passes_edge(b.probability, b.odds, min_edge)],
        initial,
        plan,
    )
    today["withoutOdds"] = today_without_odds
    today["aggressive"] = aggressive_plan(today_all, initial, target_multiple)

    return {
        "today": today,
        "params": {
            "initial": round(float(initial), 2),
            "strategy": plan.strategy,
            "stakePct": plan.stake_pct,
            "kellyMultiplier": plan.kelly_multiplier,
            "maxStakePct": plan.max_stake_pct,
            "targetMultiple": round(float(target_multiple), 2),
            "days": days,
            "sport": sport,
            "market": market,
            "minConfidence": min_confidence,
            "minEv": min_ev,
            "minEdge": round(min_edge * 100, 2) if min_edge is not None else None,
            "useCalibrated": use_calibrated,
        },
        "sample": sample,
        "backtest": backtest,
        "projection": projection,
        "monteCarlo": mc,
        "verdict": build_verdict(bets, backtest, projection, mc),
        "marketCajas": caja_by_market(
            all_market_bets, initial, plan, target_multiple, sims=sims, horizon_days=horizon_days
        ),
        "byMarket": breakdown_by_market(bets),
        "stability": temporal_stability(bets),
    }
