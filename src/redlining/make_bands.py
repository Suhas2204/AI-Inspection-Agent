"""Compatibility shim: Block 3's first step moved to redlining.prep.make_bands.

Re-exports the implementation, which is now in prep/. SRC and OUT still name
the same two files, anchored in paths.py, which did not move.

`python -m redlining.make_bands` still emits the 29 rows the advisor ranks:
it hands off to the prep module with runpy.
"""

from __future__ import annotations

from .prep.make_bands import (  # noqa: F401
    EXPECTED_DEVICE_TYPES,
    EXPECTED_DEVICES,
    EXPECTED_TERMINALS,
    OUT,
    SRC,
    STRIP_TAGS,
    load,
    main,
)

__all__ = [
    "EXPECTED_DEVICE_TYPES", "EXPECTED_DEVICES", "EXPECTED_TERMINALS", "OUT",
    "SRC", "STRIP_TAGS", "load", "main",
]


if __name__ == "__main__":
    import runpy
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("redlining.prep.make_bands", run_name="__main__")
