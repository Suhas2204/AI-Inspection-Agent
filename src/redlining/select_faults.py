"""Compatibility shim: the fault draw moved to redlining.prep.select_faults.

Re-exports the implementation, which is now in prep/. This is safe to import
now that the draw sits in main() behind a guard; while it ran at import, a
shim that re-exported anything would have performed the selection and written
a CSV just by being imported.

    uv run python -m redlining.select_faults 20260920 > data/faults.csv

sys.argv is untouched by the hand-off, so the seed argument still arrives.
"""

from __future__ import annotations

from .prep.select_faults import (  # noqa: F401
    CANDIDATES,
    DEFAULT_SEED,
    N_DETECTABLE,
    N_KNOWN_MISS,
    main,
)

__all__ = ["CANDIDATES", "DEFAULT_SEED", "N_DETECTABLE", "N_KNOWN_MISS", "main"]


if __name__ == "__main__":
    import runpy
    import warnings

    # Expected: the re-export above already imported the prep module, and
    # run_module executes it again under the name __main__ so main() runs.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("redlining.prep.select_faults", run_name="__main__")
