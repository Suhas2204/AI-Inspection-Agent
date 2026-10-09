"""Compatibility shim: Block 9 statistics moved to redlining.core.stats.

Re-exports the implementation, which is now in core/. The identity this file
has to preserve is the one tests/test_stats.py asserts: experiments/stats.py
and redlining.stats must BE one implementation, not two copies of a Wilson
interval that can drift apart while both keep passing their own tests.

No __main__ here: this module never had one. experiments/stats.py is the
runnable entry point, and it reaches core.stats directly.
"""

from __future__ import annotations

from .core.stats import (  # noqa: F401
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
