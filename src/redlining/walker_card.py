"""Compatibility shim: the walker card moved to evaluation.walker_card.

Re-exports the implementation, which is now in evaluation/, including
strip_line_v2 and load_overrides, which tests/test_walker_card.py drives
against both walker_card.txt and walker_card_v2.txt at the repository root.

`python -m redlining.walker_card` still prints the card: it hands off to the
evaluation module with runpy.
"""

from __future__ import annotations

from .evaluation.walker_card import (  # noqa: F401
    CLAUSE,
    CURRENT_VERSION,
    FAULTS,
    PREFIX,
    STRIP_NORMAL,
    STRIP_STEM,
    VERSIONS,
    card,
    load_overrides,
    main,
    strip_line_v2,
)

__all__ = [
    "CLAUSE", "CURRENT_VERSION", "FAULTS", "PREFIX", "STRIP_NORMAL",
    "STRIP_STEM", "VERSIONS", "card", "load_overrides", "main",
    "strip_line_v2",
]


if __name__ == "__main__":
    import runpy
    import warnings

    # Expected: the re-export above already imported the evaluation
    # module, and run_module executes it again as __main__ so its block runs.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("redlining.evaluation.walker_card",
                         run_name="__main__")
