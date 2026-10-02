"""Glicko-2 rating system: rating, rating deviation (RD) and volatility.

Pure math, no DB access — `elo_service.py` owns loading match history and
persisting the results. Implements Glickman's Glicko-2 spec
(http://www.glicko.net/glicko/glicko2.pdf):

- Each competitor carries a rating, an RD (uncertainty about that rating) and
  a volatility (how erratic their results have been). RD shrinks as a player
  accumulates consistent results and grows while they are inactive, which is
  exactly the "I'm less sure about this one" signal a plain Elo rating can't
  express — e.g. a short turnaround after a high-stakes result, or a long
  layoff, should widen the predicted probability toward 50% rather than being
  treated identically to a player on a long, stable run of matches.
- `rate_match` applies one single-opponent update (the n=1 case of Glickman's
  multi-opponent rating-period algorithm — mathematically exact, not an
  approximation, since our training loop processes one match at a time).
- `expected_score` is the read-only serving-time win probability for two
  arbitrary (rating, RD) pairs, using their combined RD so that
  P(a beats b) + P(b beats a) == 1 regardless of which side is queried.
"""
import math
from typing import Tuple

SCALE = 173.7178
DEFAULT_RATING = 1500.0
DEFAULT_RD = 350.0
DEFAULT_VOLATILITY = 0.06
TAU = 0.5  # system constraint on volatility change; Glickman's recommended default
RD_MAX = 350.0
PERIOD_DAYS = 7  # one Glicko-2 "rating period" = this many days of inactivity


def _rating_to_mu(rating: float) -> float:
    return (rating - DEFAULT_RATING) / SCALE


def _mu_to_rating(mu: float) -> float:
    return mu * SCALE + DEFAULT_RATING


def _rd_to_phi(rd: float) -> float:
    return rd / SCALE


def _phi_to_rd(phi: float) -> float:
    return phi * SCALE


def _g(phi: float) -> float:
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi * math.pi))


def _e(mu: float, mu_j: float, phi_j: float) -> float:
    x = -_g(phi_j) * (mu - mu_j)
    # Guard against overflow for extreme rating gaps.
    x = max(min(x, 700.0), -700.0)
    return 1.0 / (1.0 + math.exp(x))


def _update_volatility(phi: float, delta: float, v: float, sigma: float, tau: float = TAU) -> float:
    """Illinois algorithm (Glicko-2 step 5) solving for the new volatility."""
    a = math.log(sigma * sigma)
    eps = 1e-6

    def f(x: float) -> float:
        ex = math.exp(x)
        num = ex * (delta * delta - phi * phi - v - ex)
        den = 2.0 * (phi * phi + v + ex) ** 2
        return (num / den) - (x - a) / (tau * tau)

    big_a = a
    if delta * delta > phi * phi + v:
        big_b = math.log(delta * delta - phi * phi - v)
    else:
        k = 1
        while f(a - k * tau) < 0:
            k += 1
        big_b = a - k * tau

    f_a, f_b = f(big_a), f(big_b)
    while abs(big_b - big_a) > eps:
        big_c = big_a + (big_a - big_b) * f_a / (f_b - f_a)
        f_c = f(big_c)
        if f_c * f_b < 0:
            big_a, f_a = big_b, f_b
        else:
            f_a = f_a / 2.0
        big_b, f_b = big_c, f_c

    return math.exp(big_a / 2.0)


def inflate_rd_for_inactivity(rd: float, volatility: float, idle_periods: float) -> float:
    """Grow RD for time passed with no rated matches (no games -> RD-only step)."""
    if idle_periods <= 0:
        return rd
    phi = _rd_to_phi(rd)
    phi_star = math.sqrt(phi * phi + idle_periods * volatility * volatility)
    return min(_phi_to_rd(phi_star), RD_MAX)


def rate_match(
    rating: float,
    rd: float,
    volatility: float,
    opp_rating: float,
    opp_rd: float,
    score: float,
    idle_periods: float = 0.0,
    rating_bonus: float = 0.0,
) -> Tuple[float, float, float]:
    """Apply one Glicko-2 update for a single match against one opponent.

    `score` is 1.0 (win), 0.5 (draw) or 0.0 (loss), same convention as the
    Elo `home_actual`/`away_actual` values this replaces. `idle_periods` is
    the number of `PERIOD_DAYS`-sized gaps since this competitor's previous
    rated match, applied as a pre-match RD inflation before the update.

    `rating_bonus` shifts only the *expected-score* calculation (e.g. a
    home-advantage nudge), matching how the previous plain-Elo update used
    `rating + HOME_ADVANTAGE` to compute the surprise but still applied the
    resulting delta to the unadjusted rating — the bonus does not get baked
    into the persisted rating.
    """
    rd = inflate_rd_for_inactivity(rd, volatility, idle_periods)

    mu = _rating_to_mu(rating)
    mu_adj = _rating_to_mu(rating + rating_bonus)
    phi = _rd_to_phi(rd)
    mu_j = _rating_to_mu(opp_rating)
    phi_j = _rd_to_phi(opp_rd)

    g_j = _g(phi_j)
    e_val = _e(mu_adj, mu_j, phi_j)
    e_val = min(max(e_val, 1e-10), 1.0 - 1e-10)

    v = 1.0 / (g_j * g_j * e_val * (1.0 - e_val))
    delta = v * g_j * (score - e_val)

    new_volatility = _update_volatility(phi, delta, v, volatility)

    phi_star = math.sqrt(phi * phi + new_volatility * new_volatility)
    phi_new = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)
    mu_new = mu + phi_new * phi_new * g_j * (score - e_val)

    new_rating = _mu_to_rating(mu_new)
    new_rd = min(_phi_to_rd(phi_new), RD_MAX)
    return new_rating, new_rd, new_volatility


def expected_score(rating_a: float, rd_a: float, rating_b: float, rd_b: float) -> float:
    """Serving-time win probability for `a` against `b`.

    Uses their combined RD (not just the opponent's, as `rate_match`'s
    per-period update does) so the result is symmetric:
    expected_score(a, b) + expected_score(b, a) == 1.
    """
    mu_a = _rating_to_mu(rating_a)
    mu_b = _rating_to_mu(rating_b)
    phi_combined = math.sqrt(_rd_to_phi(rd_a) ** 2 + _rd_to_phi(rd_b) ** 2)
    return _e(mu_a, mu_b, phi_combined)
