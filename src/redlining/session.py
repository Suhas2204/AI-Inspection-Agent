"""Compatibility shim: the inspection loop moved to inspection.session.

Re-exports the implementation, which is now in inspection/. Read and Heard
are in the list because session re-exports them from core.reads and six test
modules import them from here -- the chain old-path -> session -> core.reads
has to end at one class.

`python -m redlining.session` still runs an inspection, with every flag it
had: --scripted, --live, --agent, --llm, --speak. It hands off to the
inspection module with runpy.
"""

from __future__ import annotations

from .inspection.session import (  # noqa: F401
    CLOSING,
    EXIT_WORDS,
    FUNCTIONS,
    GLUED_RE,
    GUARDED_FIELDS,
    KeyboardInput,
    MAX_REASKS,
    MAX_TURNS,
    NOTHING_OPEN,
    OPENING,
    ScriptedInput,
    TAG_MODE_WARNING,
    WORD_DIGITS,
    Heard,
    Read,
    _is_exit,
    _typed_listener,
    _voice_listener,
    agent_loop,
    count_tokens,
    dispatch_note,
    main,
    parse_counts,
    run,
    run_agent,
    runaway_reason,
    step_item,
    triage,
    unknown_labels,
    voice_of,
)

__all__ = [
    "CLOSING", "EXIT_WORDS", "FUNCTIONS", "GLUED_RE", "GUARDED_FIELDS",
    "Heard", "KeyboardInput", "MAX_REASKS", "MAX_TURNS", "NOTHING_OPEN",
    "OPENING", "Read", "ScriptedInput", "TAG_MODE_WARNING", "WORD_DIGITS",
    "agent_loop", "count_tokens", "dispatch_note", "main", "parse_counts",
    "run", "run_agent", "runaway_reason", "step_item", "triage",
    "unknown_labels", "voice_of",
]


if __name__ == "__main__":
    import runpy
    import warnings

    # Expected: the re-export above already imported the inspection module,
    # and run_module executes it again as __main__ so its block runs.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("redlining.inspection.session", run_name="__main__")
