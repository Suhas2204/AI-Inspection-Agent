"""Block 9: interval estimates and the one paired test the metrics need.

Two functions, and both are here because of how small this study is. One run,
70 positions, 10 planted faults. A detection rate of 9/10 and one of 90/100
print the same "90%" and mean very different things, and a table of bare
percentages invites the reader to compare numbers that cannot be
distinguished. So every rate gets its k/n and a 95% interval beside it, and
the paired comparison gets a p-value computed exactly rather than from a
chi-square approximation that does not hold at these counts.

wilson_ci, not the textbook p +/- z*sqrt(p(1-p)/n). The normal-approximation
("Wald") interval is wrong in exactly the places this study lives: at k = 0
or k = n it collapses to zero width, and at small n its coverage is far below
the nominal 95%. Our abstain rate IS 0/70 and our coverage IS 70/70, so the
Wald interval would report "0.0% to 0.0%" for both -- a certainty nobody
measured. The Wilson score interval has no such degeneracy and is the one
Brown, Cai & DasGupta (2001) recommend for small n.

mcnemar_exact, not the chi-square form. McNemar's statistic
(b-c)^2/(b+c) is a chi-square approximation, and the usual advice is to stop
trusting it once b + c is below about 25. The VAD comparison has b + c = 1.
So the p-value is the exact binomial test it approximates: under the null the
two methods are equally likely to be the one that is right on a discordant
pair, so b ~ Binomial(b+c, 1/2), computed here in exact integer arithmetic.

What is NOT given an interval, on purpose: the character error rate. A CER is
errors per reference character, which is not a binomial proportion. The
characters inside one attempt are not independent trials, and insertions let
the numerator exceed the denominator -- one runaway decode in this corpus
scores 2750%. A Wilson interval on that number would be arithmetic without
meaning. CER is reported as itself, with the per-clip table beside it.

No scipy. The normal quantile comes from statistics.NormalDist in the
standard library, and the binomial tail from math.comb, so there is nothing
to install and nothing to pin.

Why this is in src/ and not in experiments/, where the rest of the Block 9
analysis lives: src/redlining/score.py reports three of the four rates that
need an interval (fault detection, precision, abstention), and an installed
package cannot import from an experiments folder that is not packaged with
it. experiments/stats.py re-exports this module, so the experiment scripts
and the package share one implementation and the two cannot drift.
"""

from __future__ import annotations

from fractions import Fraction
from math import comb, sqrt
from statistics import NormalDist

DEFAULT_CONF = 0.95


def z_for(conf: float) -> float:
    """The two-sided normal quantile for a confidence level.

    Args:
        conf: Confidence level, strictly between 0 and 1, e.g. 0.95.

    Returns:
        z such that P(-z < Z < z) == conf. 1.959963... for 0.95.

    Raises:
        ValueError: If conf is not strictly between 0 and 1.
    """
    if not 0.0 < conf < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {conf!r}")
    return NormalDist().inv_cdf((1.0 + conf) / 2.0)


def wilson_ci(k: int, n: int, conf: float = DEFAULT_CONF
              ) -> tuple[float | None, float | None]:
    """Wilson score interval for a binomial proportion.

    The interval is not centred on k/n -- it is pulled toward 1/2, by more
    when n is small. That is the point of it, and it is why the bounds stay
    inside [0, 1] and stay non-degenerate at k = 0 and k = n where the
    normal approximation gives an interval of zero width.

    Args:
        k: Successes observed.
        n: Trials. 0 means nothing was measured.
        conf: Confidence level, e.g. 0.95.

    Returns:
        (lo, hi), each in [0, 1], and always with lo <= k/n <= hi. lo is
        exactly 0.0 at k == 0 and hi exactly 1.0 at k == n. (None, None) when
        n == 0, matching the way the scorers print a rate with an empty
        denominator as "n/a" rather than as 0%.

    Raises:
        ValueError: If k or n is negative, or k > n.
    """
    if n < 0 or k < 0:
        raise ValueError(f"k and n must be non-negative, got k={k}, n={n}")
    if k > n:
        raise ValueError(f"k must not exceed n, got k={k}, n={n}")
    if n == 0:
        return None, None

    z = z_for(conf)
    p = k / n
    z2 = z * z
    denominator = 1.0 + z2 / n
    centre = (p + z2 / (2 * n)) / denominator
    half = (z / denominator) * sqrt(p * (1.0 - p) / n + z2 / (4 * n * n))

    # The two ends are pinned exactly rather than computed. At k == 0 the
    # algebra gives centre == half, so the subtraction is a cancellation and
    # leaves float dust -- 3.5e-18 for 0/70 -- which is not a rounding
    # nicety: it breaks the lo <= k/n <= hi invariant a caller is entitled
    # to, and makes a bound that should BE zero merely near it. Same at
    # k == n for the upper end. A test holds both.
    lo = 0.0 if k == 0 else max(0.0, centre - half)
    hi = 1.0 if k == n else min(1.0, centre + half)
    return lo, hi


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar test on the two discordant counts.

    b and c are the pairs the two methods disagree about: b that only the
    first got right, c that only the second did. The pairs both got right and
    the pairs both got wrong carry no information about which is better and
    are not arguments here -- that is what makes this a paired test.

    Under the null hypothesis the two methods are equally likely to be the
    one that is right on a discordant pair, so b ~ Binomial(b + c, 1/2) and
    the two-sided p-value is twice the smaller tail. Computed in exact
    integer arithmetic via Fraction, so there is no floating-point error and
    no large-n overflow; the chi-square form this replaces is an
    approximation that should not be trusted below about b + c = 25.

    Args:
        b: Pairs the first method got right and the second got wrong.
        c: Pairs the second method got right and the first got wrong.

    Returns:
        The two-sided p-value in (0, 1]. Exactly 1.0 when b == c, including
        when both are 0: no discordant pair is no evidence either way, which
        is a result and not an error.

    Raises:
        ValueError: If b or c is negative.
    """
    if b < 0 or c < 0:
        raise ValueError(f"counts must be non-negative, got b={b}, c={c}")

    n = b + c
    if n == 0:
        return 1.0

    # One tail, up to and including the smaller count, then doubled. The cap
    # matters: at b == c the doubled tail exceeds 1 and the p-value is 1.
    smaller = min(b, c)
    tail = sum(comb(n, i) for i in range(smaller + 1))
    return min(1.0, float(Fraction(2 * tail, 2 ** n)))


def pct(x: float | None, places: int = 1) -> str:
    """Format a ratio as a percentage, or 'n/a'.

    Args:
        x: Ratio in 0..1, or None.
        places: Decimal places.

    Returns:
        e.g. "80.0%". None prints as "n/a" rather than 0%, which would read
        as a measured failure instead of an absent measurement.
    """
    return "n/a" if x is None else f"{x * 100:.{places}f}%"


def fmt_ci(lo: float | None, hi: float | None, places: int = 1) -> str:
    """Format a Wilson interval for a table.

    Args:
        lo: Lower bound, or None.
        hi: Upper bound, or None.
        places: Decimal places.

    Returns:
        e.g. "[69.2, 87.8]", or "[n/a]" when there was nothing to measure.
    """
    if lo is None or hi is None:
        return "[n/a]"
    return f"[{lo * 100:.{places}f}, {hi * 100:.{places}f}]"


def fmt_rate(k: int, n: int, conf: float = DEFAULT_CONF,
             places: int = 1) -> str:
    """Format one rate as k/n, the percentage, and its interval.

    One function so that every table in the study spells a rate the same way
    and a reader never has to check whether two of them mean the same thing.

    Args:
        k: Successes.
        n: Trials.
        conf: Confidence level.
        places: Decimal places for the percentages.

    Returns:
        e.g. "56/70   80.0%  [69.2, 87.8]".
    """
    rate = k / n if n else None
    lo, hi = wilson_ci(k, n, conf)
    return f"{k}/{n}".ljust(8) + f"{pct(rate, places):>7}  {fmt_ci(lo, hi, places)}"
