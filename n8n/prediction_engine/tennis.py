"""Tennis prediction models: Elo, Surface Elo, XGBoost-like, CatBoost-like, Ensemble."""
import json
import math
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from common import (
    confidence_from_prob,
    ev_and_kelly,
    format_probabilities,
    glicko2_expected_score,
    normalize_ranking,
    parse_form,
    poisson_pmf,
    safe_get,
    scale,
    sigmoid,
    weighted_average,
)


SURFACE_MULTIPLIERS = {
    'clay': {'clay': 1.15, 'hard': 0.95, 'grass': 0.90},
    'hard': {'clay': 0.95, 'hard': 1.10, 'grass': 0.95},
    'grass': {'clay': 0.90, 'hard': 0.95, 'grass': 1.15},
}


def parse_h2h(h2h_str: str) -> tuple:
    """Parse head-to-head string '5-4' into (p1_wins, p2_wins)."""
    if not h2h_str or h2h_str == 'N/A':
        return (0, 0)
    parts = h2h_str.split('-')
    if len(parts) != 2:
        return (0, 0)
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        return (0, 0)


def _win_rate_from_features(features: Optional[Dict[str, Any]], side: str, key: str) -> Optional[float]:
    """Extract a win rate from the FeatureService feature block."""
    if not features:
        return None
    side_features = features.get(side)
    if not side_features:
        return None
    agg = side_features.get(key)
    if isinstance(agg, dict):
        return agg.get('win_rate')
    return None


# --- Set 1 Winner: travel/jet-lag proxy -------------------------------
# A player who just flew in for a short-turnaround match -- unfamiliar
# courts/balls/crowd, body clock still elsewhere -- is a classic "slow
# starter in set 1" story. Real travel distance/timezone isn't collected
# (api-tennis gives no tournament location), so this uses the closest proxy
# buildable from data already in hand: did the player's PREVIOUS match
# (FeatureService.previous_tournament) happen in a different coarse region
# from this one, with only a few days to adjust (days_since_last_match)?
# Deliberately coarse and capped small -- a plausible proxy, not measured
# ground truth, nudging Set 1 Winner only (by set 2 a player has settled
# in; Match Winner/Total Sets/Exact Set Score are untouched).
TOURNAMENT_REGION: Dict[str, str] = {
    # North America
    'us open': 'north_america', 'indian wells': 'north_america', 'miami': 'north_america',
    'canada': 'north_america', 'toronto': 'north_america', 'montreal': 'north_america',
    'cincinnati': 'north_america', 'washington': 'north_america', 'atlanta': 'north_america',
    'houston': 'north_america', 'dallas': 'north_america', 'newport': 'north_america',
    'winston-salem': 'north_america', 'los cabos': 'north_america', 'acapulco': 'north_america',
    'mexico': 'north_america',
    # South America
    'rio de janeiro': 'south_america', 'rio open': 'south_america', 'buenos aires': 'south_america',
    'santiago': 'south_america', 'cordoba': 'south_america', 'bogota': 'south_america',
    'sao paulo': 'south_america',
    # Europe
    'wimbledon': 'europe', 'roland garros': 'europe', 'french open': 'europe',
    'monte-carlo': 'europe', 'monte carlo': 'europe', 'madrid': 'europe', 'rome': 'europe',
    'roma': 'europe', 'barcelona': 'europe', 'halle': 'europe', 'queen': 'europe',
    'hamburg': 'europe', 'vienna': 'europe', 'basel': 'europe', 'paris': 'europe',
    'rotterdam': 'europe', 'marseille': 'europe', 'montpellier': 'europe', 'metz': 'europe',
    'munich': 'europe', 'geneva': 'europe', 'lyon': 'europe', 'stuttgart': 'europe',
    'eastbourne': 'europe', 'bastad': 'europe', 'gstaad': 'europe', 'umag': 'europe',
    'kitzbuhel': 'europe', 'estoril': 'europe', 'marrakech': 'europe', 'belgrade': 'europe',
    'budapest': 'europe', 'sofia': 'europe', 'antwerp': 'europe', 'stockholm': 'europe',
    'moselle': 'europe',
    # Asia-Pacific
    'australian open': 'asia_pacific', 'shanghai': 'asia_pacific', 'beijing': 'asia_pacific',
    'tokyo': 'asia_pacific', 'china': 'asia_pacific', 'japan': 'asia_pacific',
    'adelaide': 'asia_pacific', 'brisbane': 'asia_pacific', 'auckland': 'asia_pacific',
    'chengdu': 'asia_pacific', 'zhuhai': 'asia_pacific', 'astana': 'asia_pacific',
    'seoul': 'asia_pacific', 'hong kong': 'asia_pacific', 'singapore': 'asia_pacific',
    # Middle East / Africa
    'dubai': 'middle_east_africa', 'doha': 'middle_east_africa', 'qatar': 'middle_east_africa',
    'rabat': 'middle_east_africa', 'tel aviv': 'middle_east_africa', 'almaty': 'middle_east_africa',
}

# Beyond this many days there was time to adjust even across regions; below
# it (or with no data) there's nothing to flag. Within the window, less
# elapsed time means more disruption (linear taper).
_TRAVEL_DAYS_WINDOW = (0, 4)
# Max probability taken away from the traveling player's Set 1 chances.
_TRAVEL_MAX_PENALTY = 0.04


def _tournament_region(tournament_name: Optional[str]) -> Optional[str]:
    t = (tournament_name or '').lower()
    for key, region in TOURNAMENT_REGION.items():
        if key in t:
            return region
    return None


def _travel_disruption(
    previous_tournament: Optional[str],
    current_tournament: Optional[str],
    days_since_last_match: Optional[float],
) -> float:
    """Probability penalty (0 to `_TRAVEL_MAX_PENALTY`) on this player's Set
    1 chances from a likely short-turnaround cross-region trip. Zero unless
    both tournaments are classified into DIFFERENT regions and the gap falls
    inside `_TRAVEL_DAYS_WINDOW`."""
    if days_since_last_match is None:
        return 0.0
    lo, hi = _TRAVEL_DAYS_WINDOW
    if not (lo <= days_since_last_match <= hi):
        return 0.0
    prev_region = _tournament_region(previous_tournament)
    current_region = _tournament_region(current_tournament)
    if not prev_region or not current_region or prev_region == current_region:
        return 0.0
    recency = 1.0 - (days_since_last_match - lo) / max(1, hi - lo)
    return _TRAVEL_MAX_PENALTY * recency


def _travel_adjusted_set1_probs(
    set_p1: float,
    set_p2: float,
    features: Optional[Dict[str, Any]],
    tournament: Optional[str],
) -> Tuple[float, float]:
    """Nudge the per-set win probabilities for the Set 1 Winner market only
    -- `set_p1`/`set_p2` themselves stay untouched for Total Sets/Exact Set
    Score, which have nothing to do with who looked rusty in set 1."""
    p1_features = (features or {}).get('player1') or {}
    p2_features = (features or {}).get('player2') or {}
    p1_penalty = _travel_disruption(
        p1_features.get('previous_tournament'), tournament, p1_features.get('days_since_last_match'),
    )
    p2_penalty = _travel_disruption(
        p2_features.get('previous_tournament'), tournament, p2_features.get('days_since_last_match'),
    )
    adjusted_p1 = set_p1 - p1_penalty + p2_penalty
    adjusted_p1 = min(max(adjusted_p1, 0.01), 0.99)
    return adjusted_p1, 1.0 - adjusted_p1


# --- Long layoff / injury-return rust -----------------------------------
# A player can carry a "good" ranking into a tournament despite months out
# hurt -- ATP ranking decays slowly, and protected rankings exist precisely
# so an injured player doesn't fall off the list while they're out. Glicko-2
# RD already widens the general-Elo signal's OWN uncertainty for a long gap
# (elo_service.py's idle-time inflation feeds compute_elo_tennis via p1_rd/
# p2_rd, and the reasoning text already flags "incertidumbre elevada" when
# RD >= 100) -- but the other five ensemble signals have no idea: surface
# Elo without a real surface-RD fallback, the two heuristics, the ML model
# and market odds all take a stale ranking/rating at face value. This adds
# a separate, modest penalty directly to the MATCH-LEVEL ensemble
# probability -- after the six signals are combined, not inside any one of
# them -- so it reaches every set-derived market (Total Sets, Exact Set
# Score, Set 1 Winner) together with Match Winner. Unlike the travel/jet-lag
# proxy above (deliberately Set-1-only), ring rust from a long layoff is a
# whole-match effect, not a slow-start-then-fine one.
_LAYOFF_DAYS_THRESHOLD = 45   # below this: normal rest/rotation, no adjustment
_LAYOFF_DAYS_FULL = 180       # at/above this: the full penalty applies
_LAYOFF_MAX_PENALTY = 0.06    # match-win probability taken from the returning player


def _layoff_penalty(days_since_last_match: Optional[float]) -> float:
    if days_since_last_match is None or days_since_last_match < _LAYOFF_DAYS_THRESHOLD:
        return 0.0
    span = _LAYOFF_DAYS_FULL - _LAYOFF_DAYS_THRESHOLD
    severity = min(1.0, (days_since_last_match - _LAYOFF_DAYS_THRESHOLD) / span)
    return _LAYOFF_MAX_PENALTY * severity


def _layoff_adjusted_ensemble(
    ensemble: Dict[str, Any],
    features: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Nudge the match-level ensemble probability for a player coming back
    from a long layoff, independent of what their ranking says. Returns the
    (possibly unchanged) ensemble plus debug info for reasoningData, or None
    when neither player qualifies."""
    p1_features = (features or {}).get('player1') or {}
    p2_features = (features or {}).get('player2') or {}
    p1_days = p1_features.get('days_since_last_match')
    p2_days = p2_features.get('days_since_last_match')
    p1_penalty = _layoff_penalty(p1_days)
    p2_penalty = _layoff_penalty(p2_days)
    if p1_penalty == 0.0 and p2_penalty == 0.0:
        return ensemble, None

    adjusted_p1 = ensemble['player1'] - p1_penalty + p2_penalty
    adjusted_p1 = min(max(adjusted_p1, 0.02), 0.98)
    if round(adjusted_p1, 4) == round(ensemble['player1'], 4):
        return ensemble, None  # penalties canceled out -- nothing distinguishing to report

    debug = {
        'player1DaysSinceLastMatch': p1_days,
        'player2DaysSinceLastMatch': p2_days,
        'adjustment': round(adjusted_p1 - ensemble['player1'], 4),
    }
    return {**ensemble, 'player1': adjusted_p1, 'player2': 1.0 - adjusted_p1}, debug


def rank_to_elo(rank: int, top_rating: float = 2300.0, spread: float = 250.0) -> float:
    """Convert an ATP/WTA ranking into a plausible Elo rating.

    Uses a log scale so the top-10 retain high ratings while lower-ranked
    players drop off more gradually than a linear mapping.
    """
    if rank <= 0:
        rank = 1000
    # rank 1 -> top_rating, rank 10 -> top_rating - spread, rank 100 -> top_rating - 2*spread
    return top_rating - spread * math.log10(rank)


def compute_elo_tennis(
    p1_rank: int,
    p2_rank: int,
    p1_form: float,
    p2_form: float,
    p1_elo: Optional[float] = None,
    p2_elo: Optional[float] = None,
    p1_rd: Optional[float] = None,
    p2_rd: Optional[float] = None,
) -> Dict[str, float]:
    """Compute general rating-based probabilities for tennis.

    Uses real Glicko-2 rating + RD (rating deviation) from the backend when
    available — RD widens the probability toward 50% for players with
    unreliable ratings (a debutant, someone off a long layoff) — otherwise
    falls back to a log-scaled rank-based proxy with a plain-Elo logistic.
    """
    if p1_elo is not None and p2_elo is not None:
        p1_rating = float(p1_elo)
        p2_rating = float(p2_elo)
    else:
        p1_rating = rank_to_elo(p1_rank)
        p2_rating = rank_to_elo(p2_rank)

    p1_rating += p1_form * 60
    p2_rating += p2_form * 60

    if p1_rd is not None and p2_rd is not None:
        p1_expected = glicko2_expected_score(p1_rating, p1_rd, p2_rating, p2_rd)
    else:
        p1_expected = 1.0 / (1.0 + 10.0 ** ((p2_rating - p1_rating) / 400.0))
    p2_expected = 1.0 - p1_expected

    return {
        'player1': p1_expected,
        'player2': p2_expected,
    }


def compute_surface_elo(
    p1_rank: int,
    p2_rank: int,
    p1_form: float,
    p2_form: float,
    surface: str,
    p1_aces: float,
    p2_aces: float,
    p1_surface_elo: Optional[float] = None,
    p2_surface_elo: Optional[float] = None,
    p1_surface_rd: Optional[float] = None,
    p2_surface_rd: Optional[float] = None,
) -> Dict[str, float]:
    """Compute surface-adjusted rating probabilities.

    Uses real surface-specific Glicko-2 rating + RD from the backend when
    available, otherwise falls back to base Elo + aces-based surface
    adjustment.
    """
    surface = (surface or 'hard').lower()
    base_elo = compute_elo_tennis(p1_rank, p2_rank, p1_form, p2_form)

    if p1_surface_elo is not None and p2_surface_elo is not None:
        p1_rating = float(p1_surface_elo)
        p2_rating = float(p2_surface_elo)
        if p1_surface_rd is not None and p2_surface_rd is not None:
            p1_prob = glicko2_expected_score(p1_rating, p1_surface_rd, p2_rating, p2_surface_rd)
        else:
            p1_prob = 1.0 / (1.0 + 10.0 ** ((p2_rating - p1_rating) / 400.0))
        return {'player1': p1_prob, 'player2': 1.0 - p1_prob}

    # Surface affinity adjustment based on aces average (surrogate for surface preference)
    avg_aces = (p1_aces + p2_aces) / 2.0 if p1_aces and p2_aces else 8.0
    p1_surface_bonus = 0.0
    p2_surface_bonus = 0.0

    if surface == 'clay':
        # Clay favors consistency over power; lower aces slightly favored
        p1_surface_bonus = scale(p1_aces, 4.0, 12.0, 0.04, -0.04)
        p2_surface_bonus = scale(p2_aces, 4.0, 12.0, 0.04, -0.04)
    elif surface == 'grass':
        # Grass favors power (aces)
        p1_surface_bonus = scale(p1_aces, 4.0, 12.0, -0.04, 0.04)
        p2_surface_bonus = scale(p2_aces, 4.0, 12.0, -0.04, 0.04)
    else:
        # Hard court neutral-ish
        p1_surface_bonus = scale(p1_aces, 4.0, 12.0, -0.02, 0.02)
        p2_surface_bonus = scale(p2_aces, 4.0, 12.0, -0.02, 0.02)

    p1_prob = sigmoid(scale(base_elo['player1'], 0.0, 1.0, -4.0, 4.0) + p1_surface_bonus - p2_surface_bonus)
    p2_prob = 1.0 - p1_prob

    return {
        'player1': p1_prob,
        'player2': p2_prob,
    }


def compute_xgboost_tennis(
    p1_rank: int,
    p2_rank: int,
    p1_form: float,
    p2_form: float,
    p1_aces: float,
    p2_aces: float,
    h2h: tuple,
) -> Dict[str, float]:
    """XGBoost-like heuristic for tennis."""
    rank_diff = scale(p2_rank - p1_rank, -50, 50, -1.0, 1.0)
    form_diff = p1_form - p2_form
    aces_diff = scale(p1_aces - p2_aces, -4.0, 4.0, -1.0, 1.0)
    h2h_total = max(h2h[0] + h2h[1], 1)
    h2h_diff = (h2h[0] - h2h[1]) / h2h_total

    logit_p1 = (
        rank_diff * 0.40
        + form_diff * 0.25
        + aces_diff * 0.20
        + h2h_diff * 0.15
    )
    p1_prob = sigmoid(logit_p1)
    return {
        'player1': p1_prob,
        'player2': 1.0 - p1_prob,
    }


def compute_catboost_tennis(
    p1_rank: int,
    p2_rank: int,
    surface: str,
    tournament: str,
    p1_form: float,
    p2_form: float,
    tournament_tier: int = 0,
) -> Dict[str, float]:
    """CatBoost-like heuristic handling categorical features (surface, tournament)."""
    # Surface encoded effect
    surface_weights = {
        'clay': (0.02, -0.02),
        'grass': (0.02, -0.02),
        'hard': (0.0, 0.0),
    }
    surface = (surface or 'hard').lower()
    s_p1, s_p2 = surface_weights.get(surface, (0.0, 0.0))

    # Tournament tier (Grand Slams weighted higher)
    tier_bonus = 0.0
    tournament = (tournament or '').lower()
    if 'grand slam' in tournament or 'roland garros' in tournament or 'wimbledon' in tournament or 'us open' in tournament or 'australian open' in tournament:
        tier_bonus = 0.03
    # Numeric tier from API (e.g. 2000 = Grand Slam, 1000 = Masters, 500, 250)
    if tournament_tier and tournament_tier >= 1000:
        tier_bonus += 0.02

    rank_diff = scale(p2_rank - p1_rank, -50, 50, -1.0, 1.0)
    form_diff = p1_form - p2_form

    logit_p1 = rank_diff * 0.50 + form_diff * 0.30 + s_p1 - s_p2 + tier_bonus
    p1_prob = sigmoid(logit_p1)
    return {
        'player1': p1_prob,
        'player2': 1.0 - p1_prob,
    }


def compute_odds_tennis(
    odds_player1: Optional[float],
    odds_player2: Optional[float],
) -> Optional[Dict[str, float]]:
    """Convert decimal odds to margin-normalised implied probabilities.

    Returns None if odds are missing or invalid so the ensemble can ignore
    the signal rather than being distorted by defaults.
    """
    if odds_player1 is None or odds_player2 is None:
        return None
    try:
        o1 = float(odds_player1)
        o2 = float(odds_player2)
    except (TypeError, ValueError):
        return None
    if o1 <= 1.0 or o2 <= 1.0:
        return None

    inv1 = 1.0 / o1
    inv2 = 1.0 / o2
    overround = inv1 + inv2
    if overround <= 0:
        return None

    return {
        'player1': inv1 / overround,
        'player2': inv2 / overround,
    }


def compute_ml_tennis(match: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """Get probabilities from the backend-trained XGBoost tennis model.

    Falls back to None if the model is unavailable or the request fails, so
    the ensemble can rely on the heuristic models instead.
    """
    url = os.environ.get('BACKEND_URL', 'http://backend:8000')
    api_key = os.environ.get('INTERNAL_API_KEY', '')
    endpoint = f'{url}/api/v1/internal/predict/tennis-ml'

    payload = {
        'eloPlayer1': safe_get(match, 'elo_player1'),
        'eloPlayer2': safe_get(match, 'elo_player2'),
        'eloSurfacePlayer1': safe_get(match, 'elo_surface_player1'),
        'eloSurfacePlayer2': safe_get(match, 'elo_surface_player2'),
        'rankingPlayer1': safe_get(match, 'ranking_player1'),
        'rankingPlayer2': safe_get(match, 'ranking_player2'),
        'formPlayer1': safe_get(match, 'form_player1'),
        'formPlayer2': safe_get(match, 'form_player2'),
    }

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            'Content-Type': 'application/json',
            'X-Internal-Api-Key': api_key,
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            probs = result.get('probabilities')
            if probs and 'player1' in probs and 'player2' in probs:
                return {
                    'player1': float(probs['player1']),
                    'player2': float(probs['player2']),
                }
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, KeyError, ValueError):
        pass
    return None


def compute_ml_tennis_batch(matches: List[Dict[str, Any]]) -> Optional[List[Optional[Dict[str, float]]]]:
    """Get probabilities for a batch of matches from the backend ML model.

    Returns a list aligned with the input matches. Individual entries may be
    None if the backend returns invalid data for that position. Falls back to
    None for the whole batch on transport errors.
    """
    if not matches:
        return []

    url = os.environ.get('BACKEND_URL', 'http://backend:8000')
    api_key = os.environ.get('INTERNAL_API_KEY', '')
    endpoint = f'{url}/api/v1/internal/predict/tennis-ml/batch'

    payload = {
        'matches': [
            {
                'eloPlayer1': safe_get(m, 'elo_player1'),
                'eloPlayer2': safe_get(m, 'elo_player2'),
                'eloSurfacePlayer1': safe_get(m, 'elo_surface_player1'),
                'eloSurfacePlayer2': safe_get(m, 'elo_surface_player2'),
                'rankingPlayer1': safe_get(m, 'ranking_player1'),
                'rankingPlayer2': safe_get(m, 'ranking_player2'),
                'formPlayer1': safe_get(m, 'form_player1'),
                'formPlayer2': safe_get(m, 'form_player2'),
                'features': safe_get(m, 'features'),
            }
            for m in matches
        ]
    }

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            'Content-Type': 'application/json',
            'X-Internal-Api-Key': api_key,
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            probs_list = result.get('probabilities', [])
            output = []
            for probs in probs_list:
                if probs and 'player1' in probs and 'player2' in probs:
                    output.append({
                        'player1': float(probs['player1']),
                        'player2': float(probs['player2']),
                    })
                else:
                    output.append(None)
            return output
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, KeyError, ValueError):
        pass
    return None


DEFAULT_ENSEMBLE_WEIGHTS: Dict[str, Dict[str, float]] = {
    'both': {'surface_elo': 0.25, 'elo': 0.20, 'xgboost': 0.10, 'catboost': 0.10, 'ml': 0.20, 'odds': 0.15},
    'elo_only': {'surface_elo': 0.15, 'elo': 0.20, 'xgboost': 0.15, 'catboost': 0.10, 'ml': 0.25, 'odds': 0.15},
    'rank_only': {'surface_elo': 0.10, 'elo': 0.10, 'xgboost': 0.15, 'catboost': 0.15, 'ml': 0.25, 'odds': 0.25},
}

_ENSEMBLE_WEIGHTS_CACHE: Dict[str, Any] = {}


def _fetch_ensemble_weights() -> Dict[str, Dict[str, float]]:
    """Fetch data-fitted ensemble weights from the backend, once per process.

    The backend fits these from validated/failed Match Winner outcomes (see
    ensemble_weights_service.py); falls back to the historical hardcoded
    weights if the backend is unreachable or a regime lacks enough data.
    """
    if 'weights' in _ENSEMBLE_WEIGHTS_CACHE:
        return _ENSEMBLE_WEIGHTS_CACHE['weights']

    url = os.environ.get('BACKEND_URL', 'http://backend:8000')
    api_key = os.environ.get('INTERNAL_API_KEY', '')
    endpoint = f'{url}/api/v1/internal/predict/tennis-ensemble-weights'
    weights = DEFAULT_ENSEMBLE_WEIGHTS
    req = urllib.request.Request(
        endpoint,
        headers={'X-Internal-Api-Key': api_key},
        method='GET',
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            fetched = result.get('regimes')
            if fetched and all(regime in fetched for regime in DEFAULT_ENSEMBLE_WEIGHTS):
                weights = fetched
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, ValueError):
        pass

    _ENSEMBLE_WEIGHTS_CACHE['weights'] = weights
    return weights


# --- Exact Set Score: empirical prior (redesign, 2026-10-02) ---------------
# The market used to be priced from a pure i.i.d.-per-set binomial (every set
# won with the same probability, independent of the previous one). That
# over-predicts clean sweeps for favorites and under-predicts matches going
# the distance -- exactly the shape of a market that showed a statistically
# significant loss which got WORSE over time (see bankroll_service.py's
# significance test and temporal_stability). `exact_score_prior_service.py`
# fits the empirical alternative from the full historical dataset (tens of
# thousands of matches, not just the live-era validated sample): given the
# ranking gap and best-of format, how many sets did REAL matches actually
# take? This blends that empirical distribution with the old i.i.d. one,
# weighted by how much historical data backs each (best_of, rank-gap)
# bucket -- falling back to the pure i.i.d. formula where there isn't one.

_EXACT_SCORE_PRIOR_CACHE: Dict[str, Any] = {}

# Mirrors exact_score_prior_service.RANK_BUCKETS on the backend -- keep both
# in sync if either changes.
_EXACT_SCORE_RANK_BUCKETS: Tuple[Tuple[float, float, str], ...] = (
    (0, 10, '0-10'), (10, 25, '10-25'), (25, 50, '25-50'),
    (50, 100, '50-100'), (100, float('inf'), '100+'),
)
# Pseudo-sample count at which the empirical bucket gets half the blend
# weight (shrink = samples / (samples + this)) -- same ridge-shrinkage
# pattern as ensemble_weights_service.PRIOR_STRENGTH, scaled up because
# these buckets have thousands of real samples to lean on, not dozens.
EXACT_SCORE_PRIOR_STRENGTH = 200.0


def _rank_bucket_label(rank_diff: float) -> str:
    for lo, hi, label in _EXACT_SCORE_RANK_BUCKETS:
        if lo <= rank_diff < hi:
            return label
    return _EXACT_SCORE_RANK_BUCKETS[-1][2]


def _fetch_exact_score_priors() -> Dict[str, Any]:
    """Fetch the empirical exact-set-score prior artifact, once per process."""
    if 'priors' in _EXACT_SCORE_PRIOR_CACHE:
        return _EXACT_SCORE_PRIOR_CACHE['priors']

    url = os.environ.get('BACKEND_URL', 'http://backend:8000')
    api_key = os.environ.get('INTERNAL_API_KEY', '')
    endpoint = f'{url}/api/v1/internal/predict/tennis-exact-score-prior'
    priors: Dict[str, Any] = {}
    req = urllib.request.Request(
        endpoint,
        headers={'X-Internal-Api-Key': api_key},
        method='GET',
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            priors = result.get('priors') or {}
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, ValueError):
        pass

    _EXACT_SCORE_PRIOR_CACHE['priors'] = priors
    return priors


def _empirical_sets_lost(best_of: int, rank_diff: float) -> Optional[Tuple[Dict[int, float], int, str]]:
    """Empirical P(the match winner lost k sets) for this (best_of, rank
    gap), or None if that bucket hasn't accumulated enough historical
    matches yet (see exact_score_prior_service.MIN_SAMPLES_PER_BUCKET)."""
    priors = _fetch_exact_score_priors()
    if not priors:
        return None
    label = _rank_bucket_label(rank_diff)
    key = f'bo{best_of}_{label}'
    entry = priors.get(key) or priors.get(f'bo{best_of}_unknown')
    if not entry:
        return None
    dist = {int(k): v for k, v in (entry.get('distribution') or {}).items()}
    return dist, int(entry.get('samples', 0)), key


def _iid_sets_lost(p: float, best_of: int) -> Dict[int, float]:
    """P(a player with single-set win probability p lost exactly k sets),
    GIVEN that player wins the match -- a pure reparameterization of the old
    i.i.d. exact-score formulas (same p inverted from the match probability
    by `_match_prob_to_set_prob`), expressed as a distribution instead of
    joint per-scoreline probabilities so it can be blended with the
    empirical one below."""
    q = 1.0 - p
    if best_of >= 5:
        raw = {0: p ** 3, 1: 3.0 * (p ** 3) * q, 2: 6.0 * (p ** 3) * (q ** 2)}
    else:
        raw = {0: p ** 2, 1: 2.0 * (p ** 2) * q}
    total = sum(raw.values())
    return {k: (v / total if total > 0 else 0.0) for k, v in raw.items()}


def _blend_sets_lost(p: float, best_of: int, rank_diff: float) -> Tuple[Dict[int, float], Optional[Dict[str, Any]]]:
    """Blend the i.i.d. conditional distribution with the empirical one,
    weighted by the empirical bucket's sample size. Returns (distribution,
    debug_info_or_None) -- debug_info goes straight into reasoningData so
    the blend is visible/auditable on every prediction."""
    iid = _iid_sets_lost(p, best_of)
    empirical = _empirical_sets_lost(best_of, rank_diff)
    if not empirical:
        return iid, None
    dist, samples, bucket_key = empirical
    shrink = samples / (samples + EXACT_SCORE_PRIOR_STRENGTH)
    blended = {k: shrink * dist.get(k, 0.0) + (1.0 - shrink) * iid.get(k, 0.0) for k in iid}
    debug = {'bucket': bucket_key, 'samples': samples, 'empiricalWeight': round(shrink, 3)}
    return blended, debug


def ensemble_tennis(
    elo_probs: Dict[str, float],
    surface_elo_probs: Dict[str, float],
    xgboost_probs: Dict[str, float],
    catboost_probs: Dict[str, float],
    odds_probs: Optional[Dict[str, float]] = None,
    ml_probs: Optional[Dict[str, float]] = None,
    has_real_elo: bool = False,
    has_real_surface_elo: bool = False,
) -> Dict[str, Any]:
    """Ensemble with odds, ML model and dynamic weighting based on data quality.

    Weights come from `_fetch_ensemble_weights()` (data-fitted from validated
    outcomes when available, hardcoded fallback otherwise), keyed by regime:
    both real Elo ratings available, only general Elo, or rank proxies only.
    """
    has_ml = ml_probs is not None
    has_odds = odds_probs is not None

    if has_real_elo and has_real_surface_elo:
        regime = 'both'
    elif has_real_elo:
        regime = 'elo_only'
    else:
        regime = 'rank_only'

    base_weights = _fetch_ensemble_weights().get(regime, DEFAULT_ENSEMBLE_WEIGHTS[regime])
    weights = {
        'surface_elo': base_weights['surface_elo'],
        'elo': base_weights['elo'],
        'xgboost': base_weights['xgboost'],
        'catboost': base_weights['catboost'],
        'ml': base_weights['ml'] if has_ml else 0.0,
        'odds': base_weights['odds'] if has_odds else 0.0,
    }

    values_p1 = [
        surface_elo_probs['player1'],
        elo_probs['player1'],
        xgboost_probs['player1'],
        catboost_probs['player1'],
    ]
    values_p2 = [
        surface_elo_probs['player2'],
        elo_probs['player2'],
        xgboost_probs['player2'],
        catboost_probs['player2'],
    ]
    w = [weights['surface_elo'], weights['elo'], weights['xgboost'], weights['catboost']]

    if ml_probs is not None:
        values_p1.append(ml_probs['player1'])
        values_p2.append(ml_probs['player2'])
        w.append(weights['ml'])

    if odds_probs is not None:
        values_p1.append(odds_probs['player1'])
        values_p2.append(odds_probs['player2'])
        w.append(weights['odds'])

    p1 = weighted_average(values_p1, w)
    p2 = weighted_average(values_p2, w)

    total = p1 + p2
    if total > 0:
        p1 /= total
        p2 /= total

    contributions = {
        'surface_elo': round(weights['surface_elo'], 2),
        'elo': round(weights['elo'], 2),
        'xgboost': round(weights['xgboost'], 2),
        'catboost': round(weights['catboost'], 2),
    }
    if ml_probs is not None:
        contributions['ml'] = round(weights['ml'], 2)
    if odds_probs is not None:
        contributions['odds'] = round(weights['odds'], 2)

    return {
        'player1': p1,
        'player2': p2,
        'model_contributions': contributions,
    }


GRAND_SLAMS = (
    'us open', 'wimbledon', 'australian open', 'roland garros', 'french open',
)


def best_of_sets(tournament: str, tournament_tier: int = 0) -> int:
    """Number of sets the match is played to.

    On the ATP tour only Grand Slams are best-of-5; everything else
    (Masters, 500, 250, Challengers, Finals) is best-of-3.
    """
    t = (tournament or '').lower()
    if 'grand slam' in t or any(gs in t for gs in GRAND_SLAMS):
        return 5
    if tournament_tier and int(tournament_tier) >= 2000:
        return 5
    return 3


def _match_prob_to_set_prob(match_prob: float, best_of: int = 3) -> float:
    """Invert the sets->match relation to recover the single-set win prob.

    best-of-3: P_match = p^2 * (3 - 2p)
    best-of-5: P_match = p^3 * (10 - 15p + 6p^2)

    Both curves are monotonic on [0, 1] and map 0->0, 0.5->0.5, 1->1, so a
    bisection recovers the implied probability of winning one set given the
    probability of winning the match.
    """
    target = min(max(float(match_prob), 0.0), 1.0)

    if best_of >= 5:
        def curve(p: float) -> float:
            return p ** 3 * (10.0 - 15.0 * p + 6.0 * p * p)
    else:
        def curve(p: float) -> float:
            return p * p * (3.0 - 2.0 * p)

    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if curve(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def predict_tennis(match: Dict[str, Any], ml_probs: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
    """Generate predictions for a tennis match.

    If ``ml_probs`` is provided it is used directly in the ensemble; otherwise
    the backend ML endpoint is called. This allows batching ML inference
    across many matches.
    """
    p1 = safe_get(match, 'player1', 'Player 1')
    p2 = safe_get(match, 'player2', 'Player 2')
    p1_rank = normalize_ranking(safe_get(match, 'ranking_player1'), 50)
    p2_rank = normalize_ranking(safe_get(match, 'ranking_player2'), 50)
    p1_form = parse_form(safe_get(match, 'form_player1'))
    p2_form = parse_form(safe_get(match, 'form_player2'))
    surface = safe_get(match, 'surface', 'hard')
    tournament = safe_get(match, 'tournament', '')
    tournament_tier = int(safe_get(match, 'tournament_tier', 0) or 0)
    p1_aces = float(safe_get(match, 'aces_avg_player1', 8.0) or 8.0)
    p2_aces = float(safe_get(match, 'aces_avg_player2', 8.0) or 8.0)
    h2h = parse_h2h(safe_get(match, 'h2h', '0-0'))
    p1_elo = safe_get(match, 'elo_player1')
    p2_elo = safe_get(match, 'elo_player2')
    p1_surface_elo = safe_get(match, 'elo_surface_player1')
    p2_surface_elo = safe_get(match, 'elo_surface_player2')
    p1_rd = safe_get(match, 'rating_deviation_player1')
    p2_rd = safe_get(match, 'rating_deviation_player2')
    p1_surface_rd = safe_get(match, 'rating_deviation_surface_player1')
    p2_surface_rd = safe_get(match, 'rating_deviation_surface_player2')
    odds_player1 = safe_get(match, 'odds_player1')
    odds_player2 = safe_get(match, 'odds_player2')

    # Rich features from FeatureService (form, surface form, H2H).
    # When available they override the coarse form strings and placeholder H2H.
    features = safe_get(match, 'features') or {}
    p1_win_rate = _win_rate_from_features(features, 'player1', 'last_20')
    p2_win_rate = _win_rate_from_features(features, 'player2', 'last_20')
    p1_surface_win_rate = _win_rate_from_features(features, 'player1', 'surface_last_20')
    p2_surface_win_rate = _win_rate_from_features(features, 'player2', 'surface_last_20')

    if p1_win_rate is not None:
        p1_form = p1_win_rate * 2 - 1
    if p2_win_rate is not None:
        p2_form = p2_win_rate * 2 - 1

    h2h_feature = (features.get('player1') or {}).get('h2h') or {}
    if h2h_feature.get('matches', 0) > 0:
        h2h = (int(h2h_feature.get('wins', 0)), int(h2h_feature.get('losses', 0)))
    else:
        h2h = parse_h2h(safe_get(match, 'h2h', '0-0'))

    # Real aces averages from FeatureService (match statistics history).
    p1_aces_feature = (features.get('player1') or {}).get('aces_avg')
    p2_aces_feature = (features.get('player2') or {}).get('aces_avg')
    has_real_aces = p1_aces_feature is not None and p2_aces_feature is not None
    if p1_aces_feature is not None:
        p1_aces = float(p1_aces_feature)
    if p2_aces_feature is not None:
        p2_aces = float(p2_aces_feature)

    has_real_elo = p1_elo is not None and p2_elo is not None
    has_real_surface_elo = p1_surface_elo is not None and p2_surface_elo is not None

    elo_probs = compute_elo_tennis(
        p1_rank, p2_rank, p1_form, p2_form, p1_elo, p2_elo, p1_rd, p2_rd,
    )
    surface_elo_probs = compute_surface_elo(
        p1_rank, p2_rank, p1_form, p2_form, surface, p1_aces, p2_aces,
        p1_surface_elo, p2_surface_elo, p1_surface_rd, p2_surface_rd,
    )
    xgboost_probs = compute_xgboost_tennis(p1_rank, p2_rank, p1_form, p2_form, p1_aces, p2_aces, h2h)
    catboost_probs = compute_catboost_tennis(p1_rank, p2_rank, surface, tournament, p1_form, p2_form, tournament_tier)
    odds_probs = compute_odds_tennis(odds_player1, odds_player2)
    if ml_probs is None:
        ml_probs = compute_ml_tennis(match)
    ensemble = ensemble_tennis(
        elo_probs, surface_elo_probs, xgboost_probs, catboost_probs,
        odds_probs=odds_probs,
        ml_probs=ml_probs,
        has_real_elo=has_real_elo,
        has_real_surface_elo=has_real_surface_elo,
    )
    ensemble, layoff_debug = _layoff_adjusted_ensemble(ensemble, features)

    winner_key = 'player1' if ensemble['player1'] > ensemble['player2'] else 'player2'
    winner = p1 if winner_key == 'player1' else p2
    winner_confidence = confidence_from_prob(ensemble[winner_key])
    winner_odds = odds_player1 if winner_key == 'player1' else odds_player2
    ev_kelly = ev_and_kelly(ensemble[winner_key], winner_odds)

    # Best-of-3 everywhere except Grand Slams (best-of-5).
    best_of = best_of_sets(tournament, tournament_tier)
    sets_to_win = best_of // 2 + 1  # 2 for best-of-3, 3 for best-of-5
    sets_line = sets_to_win + 0.5   # 2.5 for best-of-3, 3.5 for best-of-5

    # Probability of winning a single set, implied by the ensemble match prob
    # and the best-of format.
    set_p1 = _match_prob_to_set_prob(ensemble['player1'], best_of)
    set_p2 = 1.0 - set_p1

    # Total sets over/under the format line. "Over" = the match goes past a
    # straight-sets result. Blended with a ranking-closeness nudge because
    # i.i.d. sets underestimate long matches between evenly matched players.
    rank_diff = abs(p1_rank - p2_rank)
    closeness = sigmoid((30 - rank_diff) / 10.0)
    straight_sets_prob = set_p1 ** sets_to_win + set_p2 ** sets_to_win
    close_match_prob = 0.7 * (1.0 - straight_sets_prob) + 0.3 * closeness
    close_match_prob = min(max(close_match_prob, 0.05), 0.95)
    over_sets = close_match_prob > 0.5

    elo_source = 'real' if has_real_elo else 'estimado por ranking'
    surface_elo_source = 'real' if has_real_surface_elo else 'estimado por superficie/aces'
    uncertainty_line = ''
    if p1_rd is not None and p2_rd is not None and max(p1_rd, p2_rd) >= 100:
        shakier = p1 if p1_rd >= p2_rd else p2
        uncertainty_line = (
            f" Incertidumbre elevada en el rating de {shakier} (RD {round(max(p1_rd, p2_rd),0)}), "
            f"la probabilidad ya está ajustada hacia 50/50 por esto."
        )
    layoff_line = ''
    if layoff_debug:
        rustier = p1 if layoff_debug['adjustment'] < 0 else p2
        rustier_days = layoff_debug['player1DaysSinceLastMatch'] if rustier == p1 else layoff_debug['player2DaysSinceLastMatch']
        layoff_line = (
            f" {rustier} vuelve de {round(rustier_days)} días sin competir — probabilidad ajustada "
            f"{abs(round(layoff_debug['adjustment']*100,1))} puntos en su contra pese al ranking."
        )
    odds_line = ''
    if odds_probs is not None:
        odds_line = (
            f" Cuota implícita: {p1} {round(odds_probs['player1']*100,1)}% "
            f"vs {p2} {round(odds_probs['player2']*100,1)}%."
        )
    ml_line = ''
    if ml_probs is not None:
        ml_line = (
            f" Modelo ML: {p1} {round(ml_probs['player1']*100,1)}% "
            f"vs {p2} {round(ml_probs['player2']*100,1)}%."
        )

    feature_source = ''
    if p1_win_rate is not None or p2_win_rate is not None:
        feature_source = ' Forma real de DB disponible.'

    # Local reasoning in Spanish
    winner_reasoning = (
        f"El ensemble favorece a {winner} con {winner_confidence}% de confianza. "
        f"Ranking: {p1} #{p1_rank} vs {p2} #{p2_rank}. "
        f"Elo general ({elo_source}): {round(elo_probs['player1']*100,1)}% a {round(elo_probs['player2']*100,1)}%. "
        f"Elo en {surface} ({surface_elo_source}): {round(surface_elo_probs['player1']*100,1)}% a "
        f"{round(surface_elo_probs['player2']*100,1)}%. "
        f"H2H: {h2h[0]}-{h2h[1]}.{odds_line}{ml_line}{feature_source}{uncertainty_line}{layoff_line}"
    )

    fmt_label = 'al mejor de 5 sets (Grand Slam)' if best_of >= 5 else 'al mejor de 3 sets'
    sets_reasoning = (
        f"Partido {fmt_label}. Diferencia de ranking: {rank_diff}. "
        f"Probabilidad de más de {sets_line} sets: {round(close_match_prob*100,1)}%."
    )

    # Exact set score: each player's "sets lost given they win" distribution,
    # blended with the empirical historical frequency for this (best_of,
    # ranking gap) -- see _blend_sets_lost. Reduces to the old pure i.i.d.
    # formula when that bucket has no artifact yet (empirical_debug=None).
    p1_sets_lost, empirical_debug = _blend_sets_lost(set_p1, best_of, rank_diff)
    p2_sets_lost, _ = _blend_sets_lost(set_p2, best_of, rank_diff)
    exact_scores = {}
    for lost, prob in p1_sets_lost.items():
        exact_scores[f'{p1} {sets_to_win}-{lost}'] = ensemble['player1'] * prob
    for lost, prob in p2_sets_lost.items():
        exact_scores[f'{p2} {sets_to_win}-{lost}'] = ensemble['player2'] * prob
    best_exact = max(exact_scores, key=exact_scores.get)

    # Set 1 Winner gets its own (possibly travel-adjusted) pair of set
    # probabilities -- set_p1/set_p2 themselves stay untouched for Total
    # Sets/Exact Set Score, which aren't about who looked rusty in set 1.
    set1_p1, set1_p2 = _travel_adjusted_set1_probs(set_p1, set_p2, features, tournament)
    travel_debug = None
    if (set1_p1, set1_p2) != (set_p1, set_p2):
        travel_debug = {
            'player1DaysSinceLastMatch': (features.get('player1') or {}).get('days_since_last_match'),
            'player2DaysSinceLastMatch': (features.get('player2') or {}).get('days_since_last_match'),
            'player1PreviousTournament': (features.get('player1') or {}).get('previous_tournament'),
            'player2PreviousTournament': (features.get('player2') or {}).get('previous_tournament'),
            'adjustment': round(set1_p1 - set_p1, 4),
        }

    set1_winner = p1 if set1_p1 >= set1_p2 else p2
    set1_prob = max(set1_p1, set1_p2)

    exact_reasoning = (
        f"Marcador exacto más probable: {best_exact} "
        f"({round(exact_scores[best_exact]*100,1)}%). "
        f"Probabilidad por set derivada del ensemble: {p1} {round(set_p1*100,1)}% "
        f"vs {p2} {round(set_p2*100,1)}%."
    )

    set1_reasoning = (
        f"Ganador más probable del Set 1: {set1_winner} "
        f"({round(set1_prob*100,1)}% por set, derivado del ensemble de partido)."
        + (
            f" Ajustado por posible desgaste de viaje (llegó hace poco de un torneo en otra región)."
            if travel_debug else ""
        )
    )

    # --- EV / Kelly for the set-level markets, using the odds for those exact
    # markets parsed from api-tennis get_odds (match.oddsMarkets). ---
    odds_markets = safe_get(match, 'odds_markets') or {}

    def _combine_odds(*decimals):
        """Fair combined decimal odd for 'A or B' from the per-outcome odds."""
        inv = sum(1.0 / float(o) for o in decimals if o and float(o) > 1.0)
        return round(1.0 / inv, 3) if inv > 0 else None

    # Set 1 Winner
    _s1 = odds_markets.get('set1Winner') or {}
    _s1_p1, _s1_p2 = _s1.get('p1'), _s1.get('p2')
    set1_odd = _s1_p1 if set1_winner == p1 else _s1_p2
    set1_ev = ev_and_kelly(set1_prob, set1_odd)
    set1_odds_decimal = (
        {'player1': _s1_p1, 'player2': _s1_p2} if _s1_p1 and _s1_p2 else None
    )

    # Total Sets (Over/Under the format line) from the "Number of sets" market
    _ns = odds_markets.get('numberOfSets') or {}
    if best_of >= 5:
        over_odd = _combine_odds(_ns.get('4'), _ns.get('5'))  # 4 o 5 sets
        under_odd = _ns.get('3')
    else:
        over_odd = _ns.get('3')
        under_odd = _ns.get('2')
    sets_odd = over_odd if over_sets else under_odd
    sets_prob = close_match_prob if over_sets else (1.0 - close_match_prob)
    sets_ev = ev_and_kelly(sets_prob, sets_odd)
    sets_odds_decimal = (
        {'over': over_odd, 'under': under_odd, 'chosen': sets_odd}
        if (over_odd or under_odd) else None
    )

    # Exact Set Score from the "Set Betting" market (keys like "3:1" / "1:3")
    _sb = odds_markets.get('setBetting') or {}
    _pl, _, _sc = best_exact.rpartition(' ')
    _w, _, _l = _sc.partition('-')
    _sb_key = f'{_w}:{_l}' if _pl == p1 else f'{_l}:{_w}'
    exact_odd = _sb.get(_sb_key)
    exact_ev = ev_and_kelly(exact_scores[best_exact], exact_odd)
    exact_odds_decimal = {'chosen': exact_odd, 'key': _sb_key} if exact_odd else None

    # Total Aces over/under 15.5 — only with real per-player aces averages.
    # Expected total = combined average adjusted by surface speed, modelled
    # with a Poisson distribution over the 15.5 line (matches validation).
    aces_prediction = None
    if has_real_aces:
        surface_aces_mult = {'grass': 1.15, 'hard': 1.0, 'clay': 0.9}.get((surface or 'hard').lower(), 1.0)
        expected_aces = (p1_aces + p2_aces) * surface_aces_mult
        over_prob = 1.0 - sum(poisson_pmf(expected_aces, k) for k in range(16))
        over_prob = min(max(over_prob, 0.01), 0.99)
        aces_pick = 'Over 15.5' if over_prob >= 0.5 else 'Under 15.5'
        aces_reasoning = (
            f"Aces esperados: {round(expected_aces,1)} "
            f"({p1} promedia {round(p1_aces,1)}, {p2} {round(p2_aces,1)}, "
            f"superficie {surface} x{surface_aces_mult}). "
            f"P(más de 15.5 aces): {round(over_prob*100,1)}%."
        )
        aces_prediction = {
            'market': 'Total Aces',
            'prediction': aces_pick,
            'confidence': confidence_from_prob(max(over_prob, 1.0 - over_prob)),
            'probabilities': format_probabilities({
                'over': over_prob,
                'under': 1.0 - over_prob,
            }),
            'modelContributions': {'poisson': 1.0},
            'reasoning': aces_reasoning,
            'reasoningData': {
                'model': 'poisson_aces',
                'expectedAces': round(expected_aces, 2),
                'acesAvg': {
                    'player1': round(p1_aces, 2),
                    'player2': round(p2_aces, 2),
                },
                'surfaceMultiplier': surface_aces_mult,
            },
        }

    predictions = [
        {
            'market': 'Match Winner',
            'prediction': winner,
            'confidence': winner_confidence,
            'expectedValue': ev_kelly['expected_value'],
            'kellyFraction': ev_kelly['kelly_fraction'],
            'probabilities': format_probabilities({
                'player1': ensemble['player1'],
                'player2': ensemble['player2'],
            }),
            'modelContributions': ensemble['model_contributions'],
            'reasoning': winner_reasoning,
            'reasoningData': {
                'model': 'ensemble',
                'ranking': {'player1': p1_rank, 'player2': p2_rank},
                'surface': surface,
                'elo': format_probabilities(elo_probs),
                'surface_elo': format_probabilities(surface_elo_probs),
                'xgboost': format_probabilities(xgboost_probs),
                'catboost': format_probabilities(catboost_probs),
                'odds': format_probabilities(odds_probs) if odds_probs else None,
                'oddsDecimal': {
                    'player1': odds_player1,
                    'player2': odds_player2,
                } if odds_player1 is not None and odds_player2 is not None else None,
                'ml': format_probabilities(ml_probs) if ml_probs else None,
                'eloSource': elo_source,
                'surfaceEloSource': surface_elo_source,
                'ratingDeviation': {
                    'player1': p1_rd,
                    'player2': p2_rd,
                    'surfacePlayer1': p1_surface_rd,
                    'surfacePlayer2': p2_surface_rd,
                } if any(v is not None for v in (p1_rd, p2_rd, p1_surface_rd, p2_surface_rd)) else None,
                'tournamentTier': tournament_tier,
                'featureService': {
                    'p1WinRate': p1_win_rate,
                    'p2WinRate': p2_win_rate,
                    'p1SurfaceWinRate': p1_surface_win_rate,
                    'p2SurfaceWinRate': p2_surface_win_rate,
                    'h2h': h2h_feature,
                } if features else None,
                # 'model' stays 'ensemble' even when adjusted below -- it's
                # how ensemble_weights_service._extract_row recognizes a
                # trainable Match Winner row; the layoff nudge is reported
                # separately instead of changing it (unlike Set 1 Winner's
                # travel-adjusted model label, nothing else filters on this).
                'layoffAdjustment': layoff_debug,
            },
        },
        {
            'market': 'Total Sets',
            'prediction': f'Over {sets_line}' if over_sets else f'Under {sets_line}',
            'confidence': confidence_from_prob(max(close_match_prob, 1.0 - close_match_prob)),
            'expectedValue': sets_ev['expected_value'],
            'kellyFraction': sets_ev['kelly_fraction'],
            'probabilities': format_probabilities({
                'over': close_match_prob,
                'under': 1.0 - close_match_prob,
            }),
            'modelContributions': {'elo': 0.5, 'catboost': 0.5},
            'reasoning': sets_reasoning,
            'reasoningData': {
                'model': 'heuristic',
                'rankDifference': rank_diff,
                'bestOf': best_of,
                'line': sets_line,
                'oddsDecimal': sets_odds_decimal,
            },
        },
        {
            'market': 'Exact Set Score',
            'prediction': best_exact,
            'confidence': confidence_from_prob(exact_scores[best_exact]),
            'expectedValue': exact_ev['expected_value'],
            'kellyFraction': exact_ev['kelly_fraction'],
            'probabilities': format_probabilities(exact_scores),
            'modelContributions': ensemble['model_contributions'],
            'reasoning': exact_reasoning,
            'reasoningData': {
                'model': 'empirical_blend' if empirical_debug else 'binomial_sets',
                'setProbability': format_probabilities({
                    'player1': set_p1,
                    'player2': set_p2,
                }),
                'empiricalPrior': empirical_debug,
                'oddsDecimal': exact_odds_decimal,
            },
        },
        {
            'market': 'Set 1 Winner',
            'prediction': set1_winner,
            'confidence': confidence_from_prob(set1_prob),
            'expectedValue': set1_ev['expected_value'],
            'kellyFraction': set1_ev['kelly_fraction'],
            'probabilities': format_probabilities({
                'player1': set1_p1,
                'player2': set1_p2,
            }),
            'modelContributions': ensemble['model_contributions'],
            'reasoning': set1_reasoning,
            'reasoningData': {
                'model': 'binomial_sets_travel_adjusted' if travel_debug else 'binomial_sets',
                'setProbability': format_probabilities({
                    'player1': set1_p1,
                    'player2': set1_p2,
                }),
                'travelAdjustment': travel_debug,
                'oddsDecimal': set1_odds_decimal,
            },
        },
    ]

    if aces_prediction is not None:
        predictions.append(aces_prediction)

    return predictions
