"""Compatibility shim: Block 9's scoring moved to evaluation.score.

Re-exports the implementation, which is now in evaluation/. score() and
load_faults are the two the thesis quotes numbers from, and positions() is
the single definition of where a fault sits -- prep.select_faults takes it
from here-or-there to keep its collision check honest.

`python -m redlining.score runs/<id>` still scores a run, --latex included.
It hands off to the evaluation module with runpy.
"""

from __future__ import annotations

from .evaluation.score import (  # noqa: F401
    ABSTAIN,
    BANDS,
    DETECTABLE_YES,
    MATCH,
    band_of,
    flagged_items,
    label,
    latex,
    load_faults,
    load_run,
    main,
    pct,
    positions,
    report_text,
    score,
    scoring_position,
    tex,
)

__all__ = [
    "ABSTAIN", "BANDS", "DETECTABLE_YES", "MATCH", "band_of",
    "flagged_items", "label", "latex", "load_faults", "load_run", "main",
    "pct", "positions", "report_text", "score", "scoring_position", "tex",
]


if __name__ == "__main__":
    import runpy
    import warnings

    # Expected: the re-export above already imported the evaluation
    # module, and run_module executes it again as __main__ so its block runs.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("redlining.evaluation.score", run_name="__main__")
