"""Compatibility shim: Block 8 moved to inspection.report.

Re-exports the implementation, which is now in inspection/. RunLog has to be
one class: session.py, orchestrator.py, app.py, four test modules and
risk_coverage.py all construct or annotate against it.

`python -m redlining.report` still writes its demo run: it hands off to the
inspection module with runpy.
"""

from __future__ import annotations

from .inspection.report import (  # noqa: F401
    Annotation,
    Attempt,
    FLAGGED,
    RunLog,
    _now,
)

__all__ = [
    "Annotation", "Attempt", "FLAGGED", "RunLog",
]


if __name__ == "__main__":
    import runpy
    import warnings

    # Expected: the re-export above already imported the inspection module,
    # and run_module executes it again as __main__ so its block runs.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("redlining.inspection.report", run_name="__main__")
