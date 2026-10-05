"""Tests for experiments/stats.py against known values.

Three kinds of check, because a statistics helper tested only against its own
output is tested against nothing:

1. Published values. Wilson intervals and exact binomial p-values that are
   printed in the literature and in every textbook treatment of them.
2. Closed forms. Exact rationals the definition forces, e.g. 9 of 10
   discordant pairs one way gives 2(1+10)/2^10 and nothing else.
3. Independent recomputation. The Wilson bounds are checked by substituting
   them back into the score equation they are the roots of, and the exact
   p-value by brute-force enumeration of every coin-flip pattern. Neither
   repeats the algebra under test.

The module is loaded by path, as tests/test_vad_compare.py loads its script,
because experiments/ is not an importable package.
"""

import importlib.util
from fractions import Fraction
from itertools import product
from math import isclose, sqrt
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "experiments" / "stats.py"


@pytest.fixture(scope="module")
def st():
    """The stats module, imported by path."""
    spec = importlib.util.spec_from_file_location("stats_under_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------- quantiles

@pytest.mark.parametrize("conf, z", [
    (0.90, 1.6448536269514722),
    (0.95, 1.9599639845400545),
    (0.99, 2.5758293035489004),
])
def test_z_matches_the_standard_normal_table(st, conf, z):
    """The two-sided quantiles every table prints: 1.645, 1.960, 2.576."""
    assert isclose(st.z_for(conf), z, rel_tol=1e-9)


@pytest.mark.parametrize("conf", [0.0, 1.0, -0.1, 1.5])
def test_an_impossible_confidence_level_raises(st, conf):
    """A confidence level outside (0, 1) is a bug, not a wide interval."""
    with pytest.raises(ValueError):
        st.z_for(conf)


# ------------------------------------------------------------- wilson_ci

@pytest.mark.parametrize("k, n, lo, hi", [
    # Published Wilson 95% intervals. The 0/10 and 10/10 pair is the standard
    # illustration of why the interval is used at all: the normal
    # approximation gives zero width for both.
    (0, 10, 0.0000, 0.2775),
    (10, 10, 0.7225, 1.0000),
    (1, 20, 0.0089, 0.2361),
    (9, 10, 0.5958, 0.9821),
    (2, 100, 0.0055, 0.0700),
])
def test_wilson_matches_published_intervals(st, k, n, lo, hi):
    """Known 95% Wilson intervals, to four decimal places."""
    got_lo, got_hi = st.wilson_ci(k, n, 0.95)
    assert round(got_lo, 4) == lo
    assert round(got_hi, 4) == hi


def test_the_bounds_solve_the_score_equation_they_come_from(st):
    """Substitute the bounds back into the equation they are the roots of.

    The Wilson interval is the set of p for which the score statistic
    (p_hat - p) / sqrt(p(1-p)/n) is within z of zero. Its endpoints are
    therefore the two roots of (p_hat - p)^2 = z^2 p(1-p) / n. Checking that
    the returned numbers satisfy that equation tests the implementation
    against the definition rather than against the same algebra again.
    """
    z = st.z_for(0.95)
    for n in (5, 10, 37, 64, 70, 200):
        for k in range(1, n):            # the roots are interior for 0 < k < n
            p_hat = k / n
            for bound in st.wilson_ci(k, n, 0.95):
                left = (p_hat - bound) ** 2
                right = z * z * bound * (1 - bound) / n
                assert isclose(left, right, rel_tol=1e-9, abs_tol=1e-15), (
                    f"{k}/{n} bound {bound} does not solve the score equation")


@pytest.mark.parametrize("k, n", [(0, 10), (1, 10), (5, 10), (9, 10),
                                  (10, 10), (0, 70), (56, 70), (70, 70)])
def test_the_interval_contains_the_estimate_and_stays_in_range(st, k, n):
    """lo <= k/n <= hi, and both bounds inside [0, 1]."""
    lo, hi = st.wilson_ci(k, n)
    assert 0.0 <= lo <= k / n <= hi <= 1.0


@pytest.mark.parametrize("k, n", [(0, 10), (3, 10), (0, 70), (14, 70)])
def test_wilson_is_symmetric_under_relabelling(st, k, n):
    """Counting failures instead of successes mirrors the interval.

    If it did not, the same data would give two different answers depending
    on which outcome was called the success.
    """
    lo, hi = st.wilson_ci(k, n)
    flipped_lo, flipped_hi = st.wilson_ci(n - k, n)
    assert isclose(lo, 1 - flipped_hi, abs_tol=1e-12)
    assert isclose(hi, 1 - flipped_lo, abs_tol=1e-12)


def test_the_degenerate_cases_are_not_degenerate(st):
    """0/n and n/n get real width, which is the whole reason for Wilson.

    The normal-approximation interval is p +/- z*sqrt(p(1-p)/n), which is
    exactly 0 wide at p = 0 and p = 1. This study reports 0/70 abstains and
    70/70 coverage, so a Wald interval would claim both were certain.
    """
    lo, hi = st.wilson_ci(0, 70)
    assert lo == 0.0
    assert hi > 0.05, "0/70 must not come back as a point estimate"

    lo, hi = st.wilson_ci(70, 70)
    assert hi == 1.0
    assert lo < 0.95


def test_more_data_narrows_the_interval(st):
    """The same proportion, measured more often, is pinned down better."""
    widths = [hi - lo for hi, lo in
              ((hi, lo) for lo, hi in
               (st.wilson_ci(k, n) for k, n in
                ((1, 2), (5, 10), (50, 100), (500, 1000))))]
    assert widths == sorted(widths, reverse=True)


def test_a_higher_confidence_level_widens_the_interval(st):
    """99% must be wider than 95%, which must be wider than 90%."""
    widths = []
    for conf in (0.90, 0.95, 0.99):
        lo, hi = st.wilson_ci(9, 10, conf)
        widths.append(hi - lo)
    assert widths == sorted(widths)


def test_nothing_measured_is_not_a_measurement_of_zero(st):
    """n == 0 gives (None, None), which the tables print as n/a."""
    assert st.wilson_ci(0, 0) == (None, None)


@pytest.mark.parametrize("k, n", [(-1, 10), (3, -1), (11, 10)])
def test_impossible_counts_raise(st, k, n):
    """k > n or a negative count is a caller bug, not an edge case."""
    with pytest.raises(ValueError):
        st.wilson_ci(k, n)


# ---------------------------------------------------------- mcnemar_exact

@pytest.mark.parametrize("b, c, p", [
    # Closed forms the definition forces: a two-sided binomial test at
    # p = 1/2 on n = b + c trials, twice the tail up to min(b, c).
    (1, 0, Fraction(2, 2)),                      # 2*C(1,0)/2^1  = 1
    (2, 0, Fraction(2, 4)),                      # 2*C(2,0)/2^2  = 0.5
    (3, 0, Fraction(2, 8)),                      # 0.25
    (4, 0, Fraction(2, 16)),                     # 0.125
    (5, 0, Fraction(2, 32)),                     # 0.0625
    (6, 0, Fraction(2, 64)),                     # 0.03125, first below 0.05
    (10, 0, Fraction(2, 1024)),                  # 0.001953125
    (9, 1, Fraction(2 * (1 + 10), 1024)),        # 0.021484375
    (8, 2, Fraction(2 * (1 + 10 + 45), 1024)),   # 0.109375
])
def test_mcnemar_matches_the_exact_binomial(st, b, c, p):
    """Known exact two-sided binomial p-values at p = 1/2."""
    assert st.mcnemar_exact(b, c) == float(p)


def test_the_classic_twenty_five_discordant_pairs(st):
    """20 pairs one way and 5 the other: 2*sum(C(25,0..5))/2^25.

    Written out as the exact fraction it must equal, so the expected value
    comes from the definition and not from running the function.
    """
    expected = Fraction(2 * (1 + 25 + 300 + 2300 + 12650 + 53130), 2 ** 25)
    assert expected == Fraction(136812, 33554432)
    assert st.mcnemar_exact(20, 5) == float(expected)
    assert round(st.mcnemar_exact(20, 5), 5) == 0.00408


@pytest.mark.parametrize("b, c", [(0, 0), (1, 1), (5, 5), (40, 40)])
def test_equal_discordant_counts_give_p_of_exactly_one(st, b, c):
    """Perfect symmetry is no evidence, and the doubled tail is capped at 1."""
    assert st.mcnemar_exact(b, c) == 1.0


def test_no_discordant_pair_at_all_is_a_result_not_an_error(st):
    """b = c = 0 returns 1.0. This run's VAD comparison has b + c = 1."""
    assert st.mcnemar_exact(0, 0) == 1.0


@pytest.mark.parametrize("b, c", [(0, 1), (1, 0), (3, 7), (7, 3), (12, 2)])
def test_the_test_does_not_care_which_method_is_listed_first(st, b, c):
    """Two-sided, so swapping b and c cannot change the p-value."""
    assert st.mcnemar_exact(b, c) == st.mcnemar_exact(c, b)


def test_matches_brute_force_enumeration(st):
    """Enumerate every coin-flip pattern and sum the extreme ones.

    Independent of the implementation: no binomial coefficients, no doubling
    rule -- just all 2^n equally likely outcomes of n fair flips, keeping
    those at least as far from the centre as what was observed.
    """
    for n in range(1, 13):
        for b in range(n + 1):
            c = n - b
            observed = abs(b - n / 2)
            extreme = sum(1 for flips in product((0, 1), repeat=n)
                          if abs(sum(flips) - n / 2) >= observed)
            expected = min(1.0, float(Fraction(extreme, 2 ** n)))
            assert isclose(st.mcnemar_exact(b, c), expected, rel_tol=1e-12), (
                f"b={b}, c={c}")


@pytest.mark.parametrize("b, c", [(-1, 0), (0, -1), (-2, -3)])
def test_negative_discordant_counts_raise(st, b, c):
    """A negative count cannot come from a cross-tabulation."""
    with pytest.raises(ValueError):
        st.mcnemar_exact(b, c)


def test_p_values_are_monotone_in_the_imbalance(st):
    """Fixing b + c, a more lopsided split gives a smaller p-value."""
    n = 20
    ps = [st.mcnemar_exact(b, n - b) for b in range(n // 2, n + 1)]
    assert ps == sorted(ps, reverse=True)
    assert ps[0] == 1.0


# ---------------------------------------------------------------- display

def test_formatters_say_n_slash_a_rather_than_zero(st):
    """An absent measurement must not print as a measured zero."""
    assert st.pct(None) == "n/a"
    assert st.fmt_ci(None, None) == "[n/a]"
    assert "n/a" in st.fmt_rate(0, 0)


def test_fmt_rate_carries_k_the_rate_and_the_interval(st):
    """The one spelling every table in the study uses."""
    line = st.fmt_rate(56, 70)
    assert "56/70" in line
    assert "80.0%" in line
    assert "[69.2, 87.7]" in line


# ------------------------------------------------- the two entry points

def test_the_experiments_module_re_exports_the_package_one(st):
    """experiments/stats.py and redlining.stats must BE one implementation.

    The study quotes numbers from both src/redlining/score.py and the
    experiment scripts. Two copies of a Wilson interval that drifted apart
    would be the worst kind of bug here: both halves would keep passing
    their own tests while the thesis reported two different intervals for
    one rate. So this asserts object identity, not equal behaviour.
    """
    from redlining import stats as packaged

    for name in ("wilson_ci", "mcnemar_exact", "z_for", "pct", "fmt_ci",
                 "fmt_rate", "DEFAULT_CONF"):
        assert getattr(st, name) is getattr(packaged, name), name


def test_the_experiments_module_exports_what_it_promises(st):
    """__all__ and the module's contents agree."""
    for name in st.__all__:
        assert hasattr(st, name), name
