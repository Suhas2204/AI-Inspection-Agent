"""Compatibility shim: Block 4 moved to redlining.core.normalise.

The implementation is one module object, in core/. This file re-exports every
name it defines -- including _pre, which tests/test_normalise.py imports -- so
that `from redlining.normalise import X` keeps returning the same object as
`from redlining.core.normalise import X`. tests/test_stats.py asserts that
kind of identity for the statistics pair; the same rule applies here.

`python -m redlining.normalise` still works: it hands off to the core module
with runpy, so the demo block runs there rather than being duplicated.
"""

from __future__ import annotations

from .core.normalise import (  # noqa: F401
    CARRIER_PHRASES,
    DIGIT_WORDS,
    LEADING_FILLER,
    MAX_TOKEN_RUN,
    MAX_TOKENS,
    NOISE_WORDS,
    PART_LETTER_HOMOPHONES,
    PART_RE,
    PHONETIC,
    TEEN_TENS_WORDS,
    Normalised,
    _bare,
    _CARRIERS,
    _expand_repeats,
    _longest_run,
    _pre,
    compact,
    normalise_part,
    normalise_rating,
    normalise_tag,
    runaway,
    strip_lead_in,
    strip_leading_filler,
)

__all__ = [
    "CARRIER_PHRASES", "DIGIT_WORDS", "LEADING_FILLER", "MAX_TOKEN_RUN",
    "MAX_TOKENS", "NOISE_WORDS", "PART_LETTER_HOMOPHONES", "PART_RE",
    "PHONETIC", "TEEN_TENS_WORDS", "Normalised", "compact", "normalise_part",
    "normalise_rating", "normalise_tag", "runaway", "strip_lead_in",
    "strip_leading_filler",
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
        runpy.run_module("redlining.core.normalise", run_name="__main__")
