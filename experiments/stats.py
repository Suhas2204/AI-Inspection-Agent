"""Block 9 statistics for the experiment scripts: wilson_ci and mcnemar_exact.

This is the entry point the experiments use. The implementation is one level
down in src/redlining/core/stats.py, and this module re-exports it
unchanged -- same objects, not copies, as a test asserts.

The split is not a preference. src/redlining/score.py reports three of the
four rates that need an interval (fault detection, redline precision,
abstention), and an installed package cannot import from an experiments
folder that is not packaged with it. Putting the implementation here and
copying the formulas into src/ would give the study two Wilson intervals to
drift apart, which is the one outcome worth avoiding: the thesis quotes both
files. So the implementation sits where both can reach it, and this module
keeps experiments/stats.py as the name the analysis scripts import.

Read src/redlining/core/stats.py for the reasoning behind the two choices that
matter -- the Wilson score interval rather than the normal approximation,
and the exact binomial rather than the chi-square form of McNemar's test --
and for why the character error rate is deliberately given no interval.

Run it for a quick look at both functions over the values this study uses:

    uv run python experiments/stats.py
"""

from __future__ import annotations

from redlining.core.stats import (
    DEFAULT_CONF,
    fmt_ci,
    fmt_rate,
    mcnemar_exact,
    pct,
    wilson_ci,
    z_for,
)

__all__ = ["DEFAULT_CONF", "fmt_ci", "fmt_rate", "mcnemar_exact", "pct",
           "wilson_ci", "z_for"]


if __name__ == "__main__":
    print(f"z for 95% = {z_for(0.95):.6f}\n")
    print("  Wilson 95% intervals")
    for k, n in ((0, 10), (10, 10), (1, 20), (56, 70), (9, 10), (8, 10),
                 (0, 70), (70, 70), (62, 64), (63, 64)):
        print(f"    {fmt_rate(k, n)}")
    print("\n  Exact McNemar")
    for b, c in ((0, 0), (1, 0), (0, 1), (6, 0), (9, 1), (8, 2), (10, 0),
                 (20, 5), (5, 5)):
        print(f"    b={b:>3} c={c:>3}   p = {mcnemar_exact(b, c):.6f}")
