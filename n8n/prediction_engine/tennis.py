"""Tennis prediction models: Elo, Surface Elo, XGBoost-like, CatBoost-like, Ensemble."""
import json
import math
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from common import (
    confidence_from_prob,
    ev_and_kelly,
    format_probabilities,
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
) -> Dict[str, float]:
    """Compute general Elo probabilities for tennis.

    Uses real Elo ratings from the backend when available, otherwise falls
    back to a log-scaled rank-based proxy.
    """
    if p1_elo is not None and p2_elo is not None:
        p1_rating = float(p1_elo)
        p2_rating = float(p2_elo)
    else:
        p1_rating = rank_to_elo(p1_rank)
        p2_rating = rank_to_elo(p2_rank)

    p1_rating += p1_form * 60
    p2_rating += p2_form * 60

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
) -> Dict[str, float]:
    """Compute surface-adjusted Elo probabilities.

    Uses real surface-specific Elo ratings from the backend when available,
    otherwise falls back to base Elo + aces-based surface adjustment.
    """
    surface = (surface or 'hard').lower()
    base_elo = compute_elo_tennis(p1_rank, p2_rank, p1_form, p2_form)

    if p1_surface_elo is not None and p2_surface_elo is not None:
        p1_rating = float(p1_surface_elo)
        p2_rating = float(p2_surface_elo)
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

    When real Elo ratings are available we trust the Elo/Surface-Elo models
    more. When only rank proxies are available we lean more on the market
    odds, the trained ML model and the ranking/form heuristics.
    """
    has_ml = ml_probs is not None
    has_odds = odds_probs is not None

    if has_real_elo and has_real_surface_elo:
        weights = {
            'surface_elo': 0.25,
            'elo': 0.20,
            'xgboost': 0.10,
            'catboost': 0.10,
            'ml': 0.20 if has_ml else 0.0,
            'odds': 0.15 if has_odds else 0.0,
        }
    elif has_real_elo:
        weights = {
            'surface_elo': 0.15,
            'elo': 0.20,
            'xgboost': 0.15,
            'catboost': 0.10,
            'ml': 0.25 if has_ml else 0.0,
            'odds': 0.15 if has_odds else 0.0,
        }
    else:
        weights = {
            'surface_elo': 0.10,
            'elo': 0.10,
            'xgboost': 0.15,
            'catboost': 0.15,
            'ml': 0.25 if has_ml else 0.0,
            'odds': 0.25 if has_odds else 0.0,
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


def _match_prob_to_set_prob(match_prob: float) -> float:
    """Invert the best-of-3 relation P_match = p_set^2 * (3 - 2*p_set).

    Given the probability of winning the match, returns the implied
    probability of winning a single set (bisection on the monotonic cubic).
    """
    target = min(max(float(match_prob), 0.0), 1.0)
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        val = mid * mid * (3.0 - 2.0 * mid)
        if val < target:
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

    elo_probs = compute_elo_tennis(p1_rank, p2_rank, p1_form, p2_form, p1_elo, p2_elo)
    surface_elo_probs = compute_surface_elo(
        p1_rank, p2_rank, p1_form, p2_form, surface, p1_aces, p2_aces,
        p1_surface_elo, p2_surface_elo,
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

    winner_key = 'player1' if ensemble['player1'] > ensemble['player2'] else 'player2'
    winner = p1 if winner_key == 'player1' else p2
    winner_confidence = confidence_from_prob(ensemble[winner_key])
    winner_odds = odds_player1 if winner_key == 'player1' else odds_player2
    ev_kelly = ev_and_kelly(ensemble[winner_key], winner_odds)

    # Total sets over/under 2.5 (based on ranking closeness)
    rank_diff = abs(p1_rank - p2_rank)
    close_match_prob = sigmoid((30 - rank_diff) / 10.0)  # closer ranking -> more likely 3 sets
    over_sets = close_match_prob > 0.5

    elo_source = 'real' if has_real_elo else 'estimado por ranking'
    surface_elo_source = 'real' if has_real_surface_elo else 'estimado por superficie/aces'
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
        f"H2H: {h2h[0]}-{h2h[1]}.{odds_line}{ml_line}{feature_source}"
    )

    sets_reasoning = (
        f"Diferencia de ranking: {rank_diff}. "
        f"Probabilidad de más de 2.5 sets: {round(close_match_prob*100,1)}%."
    )

    # Set-level markets derived from the ensemble match probability with a
    # best-of-3 binomial model (P_match = p_set^2 * (3 - 2*p_set)).
    set_p1 = _match_prob_to_set_prob(ensemble['player1'])
    set_p2 = 1.0 - set_p1

    exact_scores = {
        f'{p1} 2-0': set_p1 ** 2,
        f'{p1} 2-1': 2.0 * (set_p1 ** 2) * set_p2,
        f'{p2} 2-0': set_p2 ** 2,
        f'{p2} 2-1': 2.0 * (set_p2 ** 2) * set_p1,
    }
    best_exact = max(exact_scores, key=exact_scores.get)

    set1_winner = p1 if set_p1 >= set_p2 else p2
    set1_prob = max(set_p1, set_p2)

    exact_reasoning = (
        f"Marcador exacto más probable: {best_exact} "
        f"({round(exact_scores[best_exact]*100,1)}%). "
        f"Probabilidad por set derivada del ensemble: {p1} {round(set_p1*100,1)}% "
        f"vs {p2} {round(set_p2*100,1)}%."
    )

    set1_reasoning = (
        f"Ganador más probable del Set 1: {set1_winner} "
        f"({round(set1_prob*100,1)}% por set, derivado del ensemble de partido)."
    )

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
                'tournamentTier': tournament_tier,
                'featureService': {
                    'p1WinRate': p1_win_rate,
                    'p2WinRate': p2_win_rate,
                    'p1SurfaceWinRate': p1_surface_win_rate,
                    'p2SurfaceWinRate': p2_surface_win_rate,
                    'h2h': h2h_feature,
                } if features else None,
            },
        },
        {
            'market': 'Total Sets',
            'prediction': 'Over 2.5' if over_sets else 'Under 2.5',
            'confidence': confidence_from_prob(max(close_match_prob, 1.0 - close_match_prob)),
            'probabilities': format_probabilities({
                'over': close_match_prob,
                'under': 1.0 - close_match_prob,
            }),
            'modelContributions': {'elo': 0.5, 'catboost': 0.5},
            'reasoning': sets_reasoning,
            'reasoningData': {
                'model': 'heuristic',
                'rankDifference': rank_diff,
            },
        },
        {
            'market': 'Exact Set Score',
            'prediction': best_exact,
            'confidence': confidence_from_prob(exact_scores[best_exact]),
            'probabilities': format_probabilities(exact_scores),
            'modelContributions': ensemble['model_contributions'],
            'reasoning': exact_reasoning,
            'reasoningData': {
                'model': 'binomial_sets',
                'setProbability': format_probabilities({
                    'player1': set_p1,
                    'player2': set_p2,
                }),
            },
        },
        {
            'market': 'Set 1 Winner',
            'prediction': set1_winner,
            'confidence': confidence_from_prob(set1_prob),
            'probabilities': format_probabilities({
                'player1': set_p1,
                'player2': set_p2,
            }),
            'modelContributions': ensemble['model_contributions'],
            'reasoning': set1_reasoning,
            'reasoningData': {
                'model': 'binomial_sets',
                'setProbability': format_probabilities({
                    'player1': set_p1,
                    'player2': set_p2,
                }),
            },
        },
    ]

    if aces_prediction is not None:
        predictions.append(aces_prediction)

    return predictions
