"""Tests for resolving abbreviated provider names to stored competitors."""
from types import SimpleNamespace

from src.application import tennis_stats_service as ts


def _c(*names):
    return [SimpleNamespace(name=n) for n in names]


def test_same_surname_with_a_different_initial_is_a_different_player():
    assert ts.pick_candidate("M. Ymer", _c("Ymer E.")) is None
    assert ts.pick_candidate("J. M. Cerundolo", _c("Cerundolo F.")) is None
    assert not ts.names_compatible("T. Daniel", "Daniel M.")


def test_the_right_sibling_is_picked_when_both_exist():
    pool = _c("Cerundolo F.", "Cerundolo J.M.")

    assert ts.pick_candidate("J. M. Cerundolo", pool).name == "Cerundolo J.M."
    assert ts.pick_candidate("F. Cerundolo", pool).name == "Cerundolo F."


def test_abbreviated_and_full_names_still_link():
    assert ts.pick_candidate("T. M. Etcheverry", _c("Tomas Martin Etcheverry")).name == "Tomas Martin Etcheverry"
    assert ts.pick_candidate("J-L. Struff", _c("Struff J-L.")).name == "Struff J-L."
    assert ts.pick_candidate("J-L. Struff", _c("Jan-Lennard Struff")).name == "Jan-Lennard Struff"
    assert ts.pick_candidate("R. Bautista-Agut", _c("Roberto Bautista Agut")).name == "Roberto Bautista Agut"
    assert ts.pick_candidate("D. Medvedev", _c("Medvedev D.", "Medvedev A.")).name == "Medvedev D."


def test_a_bare_surname_cannot_contradict():
    assert ts.pick_candidate("C. Alcaraz", _c("Alcaraz")).name == "Alcaraz"


def test_two_equally_plausible_candidates_resolve_to_nobody():
    assert ts.pick_candidate("A. Zverev", _c("Zverev A.", "Zverev A.M.")) is None
