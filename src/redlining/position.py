"""Compatibility shim: Block 2 moved to redlining.prep.position.

Re-exports the implementation, which is now in prep/, including _emit_row so
that the shim is a full re-export rather than the public half of one. model3d
takes frame_of from here-or-there as the single definition of which frame a
part is in; both paths give the same function object.

`python -m redlining.position` still prints the walking order: it hands off
to the prep module with runpy.
"""

from __future__ import annotations

from .prep.position import (  # noqa: F401
    DATA,
    DUCT_TYPES,
    FRAMES,
    RAIL_SNAP_MM,
    RAIL_TYPE,
    STRUCTURAL,
    _emit_row,
    build,
    frame_of,
    main,
    show,
)

__all__ = [
    "DATA", "DUCT_TYPES", "FRAMES", "RAIL_SNAP_MM", "RAIL_TYPE", "STRUCTURAL",
    "build", "frame_of", "main", "show",
]


if __name__ == "__main__":
    import runpy
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("redlining.prep.position", run_name="__main__")
