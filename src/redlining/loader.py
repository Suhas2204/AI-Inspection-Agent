"""Compatibility shim: Block 1 moved to redlining.prep.loader.

Re-exports the implementation, which is now in prep/. The two path constants
come with it, so redlining.loader.RAW and redlining.loader.OUT still name the
same two files -- anchored in paths.py, which did not move.

`python -m redlining.loader` still rebuilds the cleaned export: it hands off
to the prep module with runpy.
"""

from __future__ import annotations

from .prep.loader import (  # noqa: F401
    EXPECT_CORE,
    EXPECT_DEVICES,
    EXPECT_PART_NUMBERS,
    EXPECT_RAW,
    EXPECT_STRIPS,
    EXPECT_TERMINALS,
    FILLER_TERMS,
    MERGED_NOTE,
    OUT,
    RAW,
    STRIP_TAGS,
    WRAPPER_REASON,
    WRAPPER_TERM,
    check_gate,
    clean,
    is_filler,
    is_wrapper,
    load_raw,
    main,
    merge_wrapper_locations,
    norm,
    summarise,
    write_dropped,
)

__all__ = [
    "EXPECT_CORE", "EXPECT_DEVICES", "EXPECT_PART_NUMBERS", "EXPECT_RAW",
    "EXPECT_STRIPS", "EXPECT_TERMINALS", "FILLER_TERMS", "MERGED_NOTE", "OUT",
    "RAW", "STRIP_TAGS", "WRAPPER_REASON", "WRAPPER_TERM", "check_gate",
    "clean", "is_filler", "is_wrapper", "load_raw", "main",
    "merge_wrapper_locations", "norm", "summarise", "write_dropped",
]


if __name__ == "__main__":
    import runpy
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("redlining.prep.loader", run_name="__main__")
