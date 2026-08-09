"""Common utilities for the BrainBets prediction engine."""
import json
import math
import re
from typing import Any, Dict, List, Optional


def parse_form(form_str: Optional[str]) -> float:
    """Convert a form string like 'WWDLW' into a numeric score in [-1, 1]."""
    if not form_str or form_str == 'N/A':
        return 0.0
    form_str = form_str.upper()
    total = len(form_str)
    if total == 0:
        return 0.0
    weights = []
    for i, ch in enumerate(form_str):
        # More recent matches count more
        weight = (i + 1) / total
        if ch == 'W':
            weights.append(weight * 1.0)
        elif ch == 'D':
            weights.append(weight * 0.0)
        elif ch == 'L':
            weights.append(weight * -1.0)
        else:
            weights.append(0.0)
    score = sum(weights) / max(sum(abs(w) for w in weights), 1e-6)
    return max(-1.0, min(1.0, score))


def sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    else:
        z = math.exp(x)
        return z / (1.0 + z)


def normalize_ranking(rank: Optional[int], default: int = 100) -> int:
    """Return a sensible ranking value."""
    if rank is None or rank <= 0:
        return default
    return rank


def safe_get(d: Dict[str, Any], key: str, default: Any = None) -> Any:
    """Safe dictionary get with snake_case and camelCase support."""
    if key in d:
        return d[key]
    # try camelCase variants
    camel = key.replace('_', '')
    if camel in d:
        return d[camel]
    # try common camelCase mappings
    mappings = {
        'home_team': 'homeTeam',
        'away_team': 'awayTeam',
        'home_xg': 'homeXg',
        'away_xg': 'awayXg',
        'home_xg_against': 'homeXgAgainst',
        'away_xg_against': 'awayXgAgainst',
        'home_corners': 'homeCorners',
        'away_corners': 'awayCorners',
        'home_form': 'homeForm',
        'away_form': 'awayForm',
        'stats_data_quality': 'statsDataQuality',
        'head_to_head': 'headToHead',
        'home_position': 'homePosition',
        'away_position': 'awayPosition',
        'home_elo': 'homeElo',
        'away_elo': 'awayElo',
        'home_attack': 'homeAttack',
        'home_defense': 'homeDefense',
        'away_attack': 'awayAttack',
        'away_defense': 'awayDefense',
        'expected_home_goals': 'expectedHomeGoals',
        'expected_away_goals': 'expectedAwayGoals',
        'tournament_tier': 'tournamentTier',
        'ground_type': 'groundType',
        'country_player1': 'countryPlayer1',
        'country_player2': 'countryPlayer2',
        'player1': 'player1',
        'player2': 'player2',
        'ranking_player1': 'rankingPlayer1',
        'ranking_player2': 'rankingPlayer2',
        'form_player1': 'formPlayer1',
        'form_player2': 'formPlayer2',
        'aces_avg_player1': 'acesAvgPlayer1',
        'aces_avg_player2': 'acesAvgPlayer2',
        'elo_player1': 'eloPlayer1',
        'elo_player2': 'eloPlayer2',
        'elo_surface_player1': 'eloSurfacePlayer1',
        'elo_surface_player2': 'eloSurfacePlayer2',
        'odds_player1': 'oddsPlayer1',
        'odds_player2': 'oddsPlayer2',
        'home_odds': 'homeOdds',
        'draw_odds': 'drawOdds',
        'away_odds': 'awayOdds',
        'surface': 'surface',
        'h2h': 'h2h',
    }
    if key in mappings and mappings[key] in d:
        return d[mappings[key]]
    return default


def scale(value: float, old_min: float, old_max: float, new_min: float, new_max: float) -> float:
    """Scale a value from one range to another."""
    if old_max == old_min:
        return (new_min + new_max) / 2.0
    return new_min + (value - old_min) * (new_max - new_min) / (old_max - old_min)


def confidence_from_prob(prob: float) -> int:
    """Convert a probability to a confidence score (1-99).

    Maps the raw probability directly to a percentage so close matches
    (probability near 0.5) receive low confidence and lopsided matches
    receive high confidence."""
    if prob is None:
        return 50
    return max(1, min(99, int(round(float(prob) * 100))))


def poisson_pmf(lam: float, k: int) -> float:
    """Poisson probability mass function P(X=k)."""
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def weighted_average(values: List[float], weights: List[float]) -> float:
    """Compute weighted average."""
    total_weight = sum(weights)
    if total_weight == 0:
        return sum(values) / len(values) if values else 0.0
    return sum(v * w for v, w in zip(values, weights)) / total_weight


def format_probabilities(probs: Dict[str, float]) -> Dict[str, float]:
    """Round probabilities for readability."""
    return {k: round(v, 4) for k, v in probs.items()}


def ev_and_kelly(prob: Optional[float], decimal_odds: Optional[float]) -> Dict[str, Optional[float]]:
    """Compute expected value (edge) and Kelly criterion fraction for a bet.

    EV = p * odds - 1 (e.g. 0.08 means an 8% edge over the bookmaker's
    implied probability). Kelly = (b*p - q) / b with b = odds - 1 and
    q = 1 - p, floored at 0 (a negative edge means "do not bet").
    Returns None fields when odds/prob are missing or degenerate.
    """
    empty = {'expected_value': None, 'kelly_fraction': None}
    if prob is None or decimal_odds is None:
        return empty
    try:
        p = float(prob)
        o = float(decimal_odds)
    except (TypeError, ValueError):
        return empty
    if o <= 1.0 or p <= 0.0 or p >= 1.0:
        return empty
    ev = p * o - 1.0
    b = o - 1.0
    kelly = (b * p - (1.0 - p)) / b
    return {
        'expected_value': round(ev, 4),
        'kelly_fraction': round(max(0.0, kelly), 4),
    }
