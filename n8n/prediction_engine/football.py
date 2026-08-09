"""Football prediction models: Elo, Poisson, XGBoost-like, Ensemble."""
import math
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


def compute_elo(
    home_rank: int,
    away_rank: int,
    home_form_score: float,
    away_form_score: float,
    home_elo: Optional[float] = None,
    away_elo: Optional[float] = None,
) -> Dict[str, float]:
    """Compute Elo-style probabilities for a football match.

    Uses real Elo ratings from the backend when available, otherwise falls
    back to rank-based proxies.
    """
    if home_elo is not None and away_elo is not None:
        home_rating = float(home_elo)
        away_rating = float(away_elo)
    else:
        # Base rating from inverse ranking (lower rank = higher rating)
        home_rating = scale(home_rank, 1, 100, 2000, 1200)
        away_rating = scale(away_rank, 1, 100, 2000, 1200)

    # Apply form adjustment
    home_rating += home_form_score * 50
    away_rating += away_form_score * 50

    # Home advantage
    home_rating += 65

    # Expected scores
    home_expected = 1.0 / (1.0 + 10.0 ** ((away_rating - home_rating) / 400.0))
    away_expected = 1.0 / (1.0 + 10.0 ** ((home_rating - away_rating) / 400.0))

    # Draw probability (inversely related to rating difference)
    diff = abs(home_rating - away_rating)
    draw_prob = max(0.15, min(0.35, 0.30 - diff / 800.0))

    # Normalize
    total = home_expected + away_expected + draw_prob
    return {
        'home': home_expected / total,
        'draw': draw_prob / total,
        'away': away_expected / total,
    }


def compute_poisson(
    home_xg: float,
    away_xg: float,
    home_form_score: float,
    away_form_score: float,
    home_xg_against: Optional[float] = None,
    away_xg_against: Optional[float] = None,
) -> Dict[str, Any]:
    """Compute Poisson-based probabilities and expected scores."""
    # When real defensive xG is available, blend it with the opponent's attack xG.
    if home_xg_against is not None and away_xg is not None:
        away_lambda = max(0.1, (away_xg + home_xg_against) / 2.0)
    else:
        away_lambda = max(0.1, away_xg)

    if away_xg_against is not None and home_xg is not None:
        home_lambda = max(0.1, (home_xg + away_xg_against) / 2.0)
    else:
        home_lambda = max(0.1, home_xg)

    # Adjust by form (milder adjustment to avoid over-inflating totals)
    home_lambda = max(0.1, home_lambda * (1.0 + home_form_score * 0.1))
    away_lambda = max(0.1, away_lambda * (1.0 + away_form_score * 0.1))

    # Score distribution up to 5 goals
    home_dist = [poisson_pmf(home_lambda, k) for k in range(6)]
    away_dist = [poisson_pmf(away_lambda, k) for k in range(6)]

    # Match outcome probabilities
    home_win = 0.0
    away_win = 0.0
    draw = 0.0
    score_matrix = []
    for h_goals, h_prob in enumerate(home_dist):
        row = []
        for a_goals, a_prob in enumerate(away_dist):
            joint = h_prob * a_prob
            row.append({'home': h_goals, 'away': a_goals, 'prob': joint})
            if h_goals > a_goals:
                home_win += joint
            elif h_goals < a_goals:
                away_win += joint
            else:
                draw += joint

    # Normalize
    total = home_win + draw + away_win
    if total > 0:
        home_win /= total
        draw /= total
        away_win /= total

    return {
        'home_lambda': home_lambda,
        'away_lambda': away_lambda,
        'home_win': home_win,
        'draw': draw,
        'away_win': away_win,
        'expected_home_goals': home_lambda,
        'expected_away_goals': away_lambda,
    }


def compute_h2h_adjustment(h2h: Optional[Dict[str, Any]]) -> float:
    """Return a small adjustment [-0.15, 0.15] based on head-to-head record."""
    if not h2h or not h2h.get('matches'):
        return 0.0
    home_wins = h2h.get('home_wins', 0)
    away_wins = h2h.get('away_wins', 0)
    total = h2h.get('matches', 0)
    if total == 0:
        return 0.0
    # Positive favours home, negative favours away.
    return scale((home_wins - away_wins) / total, -1.0, 1.0, -0.15, 0.15)


def compute_xgboost_like(
    home_rank: int,
    away_rank: int,
    home_xg: float,
    away_xg: float,
    home_form_score: float,
    away_form_score: float,
    home_corners: float,
    away_corners: float,
    h2h: Optional[Dict[str, Any]] = None,
) -> Dict[str, float]:
    """XGBoost-like heuristic model based on available features."""
    # Feature vector normalization
    rank_diff = scale(away_rank - home_rank, -50, 50, -1.0, 1.0)
    xg_diff = scale(home_xg - away_xg, -1.5, 1.5, -1.0, 1.0)
    form_diff = home_form_score - away_form_score
    corners_diff = scale(home_corners - away_corners, -5, 5, -1.0, 1.0)
    h2h_adj = compute_h2h_adjustment(h2h)

    # Logit-like combination
    logit_home = (
        rank_diff * 0.30
        + xg_diff * 0.30
        + form_diff * 0.20
        + corners_diff * 0.10
        + h2h_adj * 0.10
    )
    home_prob = sigmoid(logit_home + 0.2)  # +0.2 for home advantage
    away_prob = sigmoid(-logit_home - 0.2)
    draw_prob = max(0.15, 0.30 - abs(home_prob - away_prob))

    total = home_prob + away_prob + draw_prob
    return {
        'home': home_prob / total,
        'draw': draw_prob / total,
        'away': away_prob / total,
    }


def compute_odds_football(
    home_odds: Optional[float],
    draw_odds: Optional[float],
    away_odds: Optional[float],
) -> Optional[Dict[str, float]]:
    """Convert decimal 1X2 odds to margin-normalised implied probabilities."""
    if home_odds is None or draw_odds is None or away_odds is None:
        return None
    try:
        o1, ox, o2 = float(home_odds), float(draw_odds), float(away_odds)
    except (TypeError, ValueError):
        return None
    if o1 <= 1.0 or ox <= 1.0 or o2 <= 1.0:
        return None

    inv1, invx, inv2 = 1.0 / o1, 1.0 / ox, 1.0 / o2
    overround = inv1 + invx + inv2
    if overround <= 0:
        return None

    return {
        'home': inv1 / overround,
        'draw': invx / overround,
        'away': inv2 / overround,
    }


def ensemble_football(
    elo_probs: Dict[str, float],
    poisson_probs: Dict[str, Any],
    xgboost_probs: Dict[str, float],
    odds_probs: Optional[Dict[str, float]] = None,
    has_real_data: bool = False,
) -> Dict[str, Any]:
    """Ensemble with odds and dynamic weighting based on data quality.

    When real Elo/Poisson data is available we trust the model-based signals
    more. When only fallback proxies are available we lean more on the market
    odds, which are usually better calibrated for low-information matches.
    """
    if odds_probs is not None:
        if has_real_data:
            weights = {'elo': 0.20, 'poisson': 0.30, 'xgboost': 0.30, 'odds': 0.20}
        else:
            weights = {'elo': 0.10, 'poisson': 0.20, 'xgboost': 0.25, 'odds': 0.45}
    else:
        if has_real_data:
            weights = {'elo': 0.25, 'poisson': 0.35, 'xgboost': 0.40, 'odds': 0.0}
        else:
            weights = {'elo': 0.20, 'poisson': 0.30, 'xgboost': 0.50, 'odds': 0.0}

    values_home = [elo_probs['home'], poisson_probs['home_win'], xgboost_probs['home']]
    values_draw = [elo_probs['draw'], poisson_probs['draw'], xgboost_probs['draw']]
    values_away = [elo_probs['away'], poisson_probs['away_win'], xgboost_probs['away']]
    w = [weights['elo'], weights['poisson'], weights['xgboost']]

    if odds_probs is not None:
        values_home.append(odds_probs['home'])
        values_draw.append(odds_probs['draw'])
        values_away.append(odds_probs['away'])
        w.append(weights['odds'])

    home = weighted_average(values_home, w)
    draw = weighted_average(values_draw, w)
    away = weighted_average(values_away, w)

    total = home + draw + away
    if total > 0:
        home /= total
        draw /= total
        away /= total

    contributions = {
        'elo': round(weights['elo'], 2),
        'poisson': round(weights['poisson'], 2),
        'xgboost': round(weights['xgboost'], 2),
    }
    if odds_probs is not None:
        contributions['odds'] = round(weights['odds'], 2)

    return {
        'home': home,
        'draw': draw,
        'away': away,
        'expected_home_goals': poisson_probs['expected_home_goals'],
        'expected_away_goals': poisson_probs['expected_away_goals'],
        'model_contributions': contributions,
    }


def _is_fallback_data(match: Dict[str, Any]) -> bool:
    """Return True when no real Elo/Poisson/rank/form data is available."""
    has_elo = safe_get(match, 'home_elo') is not None and safe_get(match, 'away_elo') is not None
    has_poisson = (
        safe_get(match, 'home_attack') is not None
        and safe_get(match, 'away_attack') is not None
    )
    has_rank = (
        safe_get(match, 'home_position') not in (None, 0)
        and safe_get(match, 'away_position') not in (None, 0)
    )
    has_real_stats = safe_get(match, 'stats_data_quality') == 'real'
    return not (has_elo or has_poisson or has_rank or has_real_stats)


def predict_football(match: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate predictions for a football match."""
    home_team = safe_get(match, 'home_team', 'Home')
    away_team = safe_get(match, 'away_team', 'Away')
    home_rank = normalize_ranking(safe_get(match, 'home_position'), 50)
    away_rank = normalize_ranking(safe_get(match, 'away_position'), 50)
    home_elo = safe_get(match, 'home_elo')
    away_elo = safe_get(match, 'away_elo')
    home_xg = float(safe_get(match, 'home_xg', 1.5) or 1.5)
    away_xg = float(safe_get(match, 'away_xg', 1.2) or 1.2)
    home_xg_against = safe_get(match, 'home_xg_against')
    away_xg_against = safe_get(match, 'away_xg_against')
    home_form = parse_form(safe_get(match, 'home_form'))
    away_form = parse_form(safe_get(match, 'away_form'))
    home_corners = float(safe_get(match, 'home_corners', 5.0) or 5.0)
    away_corners = float(safe_get(match, 'away_corners', 5.0) or 5.0)
    h2h = safe_get(match, 'head_to_head')

    # Use Poisson xG from backend feature store when available
    expected_home_goals = safe_get(match, 'expected_home_goals')
    expected_away_goals = safe_get(match, 'expected_away_goals')
    if expected_home_goals is not None and expected_away_goals is not None:
        home_xg = float(expected_home_goals)
        away_xg = float(expected_away_goals)

    fallback = _is_fallback_data(match)
    if fallback:
        # When no real data exists, lower-tier matches tend to be low scoring.
        # Use conservative xG so totals default to Under/BTTS No.
        home_xg = 1.2
        away_xg = 1.0
        home_xg_against = None
        away_xg_against = None

    home_odds = safe_get(match, 'home_odds')
    draw_odds = safe_get(match, 'draw_odds')
    away_odds = safe_get(match, 'away_odds')
    odds_probs = compute_odds_football(home_odds, draw_odds, away_odds)

    elo_probs = compute_elo(home_rank, away_rank, home_form, away_form, home_elo, away_elo)
    poisson_result = compute_poisson(
        home_xg, away_xg, home_form, away_form,
        home_xg_against=home_xg_against, away_xg_against=away_xg_against,
    )
    xgboost_probs = compute_xgboost_like(
        home_rank, away_rank, home_xg, away_xg,
        home_form, away_form, home_corners, away_corners,
        h2h=h2h,
    )
    ensemble = ensemble_football(
        elo_probs, poisson_result, xgboost_probs,
        odds_probs=odds_probs,
        has_real_data=not fallback,
    )

    # Determine winner prediction
    winner_map = {'home': home_team, 'away': away_team, 'draw': 'Draw'}
    winner_key = max(ensemble, key=lambda k: ensemble[k] if k in ('home', 'away', 'draw') else -1)
    winner = winner_map[winner_key]
    winner_confidence = confidence_from_prob(ensemble[winner_key])
    winner_odds = {'home': home_odds, 'draw': draw_odds, 'away': away_odds}[winner_key]
    ev_kelly = ev_and_kelly(ensemble[winner_key], winner_odds)

    # Over/Under 2.5
    expected_total = ensemble['expected_home_goals'] + ensemble['expected_away_goals']
    over_prob = sigmoid((expected_total - 2.5) * 2.0)
    # Require a clear edge: predict Over only when expected total is well above 2.5.
    over_25 = expected_total > 2.8

    # BTTS
    btts_prob = (
        (1.0 - poisson_pmf(ensemble['expected_home_goals'], 0))
        * (1.0 - poisson_pmf(ensemble['expected_away_goals'], 0))
    )
    # Require a clear edge for Yes; default to No in low-information scenarios.
    btts = btts_prob > 0.58

    # Build local reasoning strings in Spanish
    data_quality = 'datos reales' if not fallback else 'datos limitados (fallback)'
    odds_line = ''
    if odds_probs is not None:
        odds_line = (
            f" Cuota implícita: {round(odds_probs['home']*100,1)}% local, "
            f"{round(odds_probs['draw']*100,1)}% empate, {round(odds_probs['away']*100,1)}% visitante."
        )

    # External consensus (shadow mode: tracked but weight 0 in the ensemble)
    expert = match.get('expertConsensus') or match.get('expert_consensus') or None
    expert_line = ''
    if expert and expert.get('homeWinPct') is not None and expert.get('awayWinPct') is not None:
        hp = expert['homeWinPct']
        ap = expert['awayWinPct']
        expert_fav = home_team if hp >= ap else away_team
        expert_line = (
            f" ClubElo (referencia externa) favorece a {expert_fav} "
            f"con {max(hp, ap)}% vs {min(hp, ap)}% (sin contar el empate)."
        )

    winner_reasoning = (
        f"El modelo ensemble favorece a {winner} con {winner_confidence}% de confianza ({data_quality}). "
        f"Elo asigna probabilidades {round(elo_probs['home']*100,1)}% local, "
        f"{round(elo_probs['draw']*100,1)}% empate y {round(elo_probs['away']*100,1)}% visitante. "
        f"Poisson espera un marcador aproximado de {ensemble['expected_home_goals']:.1f}-{ensemble['expected_away_goals']:.1f}. "
        f"Contribuciones: Elo {int(ensemble['model_contributions'].get('elo',0)*100)}%, "
        f"Poisson {int(ensemble['model_contributions'].get('poisson',0)*100)}%, "
        f"XGBoost {int(ensemble['model_contributions'].get('xgboost',0)*100)}%."
        f"{odds_line}"
        f"{expert_line}"
    )

    over_under_reasoning = (
        f"Se esperan {expected_total:.1f} goles totales. "
        f"Poisson da {round(over_prob*100,1)}% de probabilidad de Over 2.5 y "
        f"{round((1-over_prob)*100,1)}% de Under 2.5."
    )

    btts_reasoning = (
        f"Poisson estima {ensemble['expected_home_goals']:.1f} goles local y "
        f"{ensemble['expected_away_goals']:.1f} visitante. "
        f"Probabilidad de que ambos marquen: {round(btts_prob*100,1)}%."
    )

    predictions = [
        {
            'market': 'Match Winner',
            'prediction': winner,
            'confidence': winner_confidence,
            'expectedValue': ev_kelly['expected_value'],
            'kellyFraction': ev_kelly['kelly_fraction'],
            'probabilities': format_probabilities({
                'home': ensemble['home'],
                'draw': ensemble['draw'],
                'away': ensemble['away'],
            }),
            'modelContributions': ensemble['model_contributions'],
            'reasoning': winner_reasoning,
            'reasoningData': {
                'model': 'ensemble',
                'dataQuality': data_quality,
                'expectedScore': f"{ensemble['expected_home_goals']:.1f}-{ensemble['expected_away_goals']:.1f}",
                'elo': format_probabilities(elo_probs),
                'poisson': {
                    'homeWin': round(poisson_result['home_win'], 4),
                    'draw': round(poisson_result['draw'], 4),
                    'awayWin': round(poisson_result['away_win'], 4),
                },
                'xgboost': format_probabilities(xgboost_probs),
                'odds': format_probabilities(odds_probs) if odds_probs else None,
                'oddsDecimal': {
                    'home': home_odds,
                    'draw': draw_odds,
                    'away': away_odds,
                } if home_odds is not None and draw_odds is not None and away_odds is not None else None,
                'headToHead': h2h,
                'expertConsensus': expert,
                'homeForm': safe_get(match, 'home_form'),
                'awayForm': safe_get(match, 'away_form'),
                'homePosition': safe_get(match, 'home_position'),
                'awayPosition': safe_get(match, 'away_position'),
            },
        },
        {
            'market': 'Over/Under 2.5 Goals',
            'prediction': 'Over 2.5' if over_25 else 'Under 2.5',
            'confidence': confidence_from_prob(max(over_prob, 1.0 - over_prob)),
            'probabilities': format_probabilities({
                'over': over_prob,
                'under': 1.0 - over_prob,
            }),
            'modelContributions': {'poisson': 1.0},
            'reasoning': over_under_reasoning,
            'reasoningData': {
                'model': 'poisson',
                'expectedTotalGoals': round(expected_total, 2),
            },
        },
        {
            'market': 'Both Teams To Score',
            'prediction': 'Yes' if btts else 'No',
            'confidence': confidence_from_prob(max(btts_prob, 1.0 - btts_prob)),
            'probabilities': format_probabilities({
                'yes': btts_prob,
                'no': 1.0 - btts_prob,
            }),
            'modelContributions': {'poisson': 1.0},
            'reasoning': btts_reasoning,
            'reasoningData': {
                'model': 'poisson',
                'expectedHomeGoals': round(ensemble['expected_home_goals'], 2),
                'expectedAwayGoals': round(ensemble['expected_away_goals'], 2),
            },
        },
    ]

    return predictions
