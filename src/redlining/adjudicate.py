"""Compatibility shim: Block 6 moved to redlining.core.adjudicate.

Re-exports every name the implementation defines, so that a verdict compared
across the two import paths compares as the same class -- `isinstance` and
`is` both hold, because there is one module object behind both names.

`python -m redlining.adjudicate` still prints the schematic summary: it hands
off to the core module with runpy rather than duplicating the block.
"""

from __future__ import annotations

from .core.adjudicate import (  # noqa: F401
    ABSTAIN,
    COUNT_END_BRACKETS,
    END_BRACKET_TYPE,
    MATCH,
    MISMATCH,
    NO_PRINTED_PART,
    NOT_IN_SCHEMATIC,
    PART_EDIT_MAX,
    STRIP_TAGS,
    TAG_EDIT_MAX,
    Adjudicator,
    Verdict,
    edit_distance,
    terminal_functions,
)

__all__ = [
    "ABSTAIN", "COUNT_END_BRACKETS", "END_BRACKET_TYPE", "MATCH", "MISMATCH",
    "NO_PRINTED_PART", "NOT_IN_SCHEMATIC", "PART_EDIT_MAX", "STRIP_TAGS",
    "TAG_EDIT_MAX", "Adjudicator", "Verdict", "edit_distance",
    "terminal_functions",
]


if __name__ == "__main__":
    import runpy
    import warnings

    # The re-export above has already imported the core module, which is what
    # runpy warns about: run_module executes it a second time, under the name
    # __main__, so the demo block runs. That second namespace is harmless --
    # the block only reads and prints -- and it is the price of keeping one
    # copy of the demo instead of two.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("redlining.core.adjudicate", run_name="__main__")
