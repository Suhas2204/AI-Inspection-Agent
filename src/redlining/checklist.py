"""Compatibility shim: Block 3's code half moved to redlining.prep.checklist.

Re-exports the implementation, which is now in prep/. Item in particular has
to be one class across both paths: session.py, orchestrator.py, model3d.py
and six test modules all annotate against it, and two Items that merely look
alike would make `isinstance` lie.

`python -m redlining.checklist` still prints the checklist: it hands off to
the prep module with runpy.
"""

from __future__ import annotations

from .prep.checklist import (  # noqa: F401
    FRAME_ORDER,
    Item,
    load_bands,
    load_checklist,
)

__all__ = ["FRAME_ORDER", "Item", "load_bands", "load_checklist"]


if __name__ == "__main__":
    import runpy
    import warnings

    # Expected: the re-export above already imported the prep module, and
    # run_module executes it again under the name __main__ so its block runs.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("redlining.prep.checklist", run_name="__main__")
