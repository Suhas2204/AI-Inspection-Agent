"""Tests for Block 7 (session.py): the strip-count parser and the run loop."""

import json

import pytest

from redlining.adjudicate import ABSTAIN, Adjudicator
from redlining.checklist import load_checklist
from redlining.paths import SCHEMATIC
from redlining.report import RunLog
from redlining.session import (
    MAX_REASKS,
    Read,
    ScriptedInput,
    parse_counts,
    run,
    step_item,
)


@pytest.mark.parametrize("text, expected", [
    ("N 8 L 8 PE 8", {"N": 8, "L": 8, "PE": 8}),
    ("N eight L eight PE eight", {"N": 8, "L": 8, "PE": 8}),
    ("L 3 N 1", {"L": 3, "N": 1}),
    ("3 L N 1", {"L": 3, "N": 1}),
    ("3L N1", {"L": 3, "N": 1}),
    ("PE8 3L", {"PE": 8, "L": 3}),
    ("BRACKET 1", {"BRACKET": 1}),
    ("1 BRACKET", {"BRACKET": 1}),
    ("N: 8, L: 8", {"N": 8, "L": 8}),
])
def test_counts_are_parsed(text, expected):
    """Digits or words, glued or spaced, count before or after its function."""
    assert parse_counts(text) == expected


@pytest.mark.parametrize("text", ["", "You", "hello there"])
def test_nothing_to_parse_gives_empty_dict(text):
    """Empty or stray transcripts (like the live-run 'You') invent no counts."""
    assert parse_counts(text) == {}


def test_stray_words_do_not_invent_functions():
    """Unknown words between pairs are ignored."""
    assert parse_counts("N 8 hello L 8") == {"N": 8, "L": 8}


# --------------------------------------------------------------- the run loop

@pytest.fixture(scope="module")
def adj() -> Adjudicator:
    """Adjudicator loaded once per module from the cleaned schematic."""
    return Adjudicator.from_export(SCHEMATIC)


@pytest.fixture(scope="module")
def five_items() -> list:
    """The first five checklist items, in band-then-position order."""
    return load_checklist()[:5]


def recorded(log: RunLog) -> list[dict]:
    """Attempts as written to attempts.jsonl, minus the volatile timestamp.

    Args:
        log: RunLog whose attempts file is read.

    Returns:
        One dict per attempt, in the order they were recorded.
    """
    lines = log.attempts_path.read_text(encoding="utf-8").splitlines()
    return [{k: v for k, v in json.loads(line).items() if k != "at"}
            for line in lines]


class SilentInput:
    """Input that never yields a value, so every read abstains.

    It counts its calls, which is how the test sees how often it was asked.
    """

    _tag = ""

    def __init__(self):
        """Start with no calls recorded."""
        self.calls = 0

    def device(self, prompt: str, attempt: int) -> Read:
        """Return an empty device read.

        Args:
            prompt: Ignored.
            attempt: Ignored.

        Returns:
            Read with nothing in it.
        """
        self.calls += 1
        return Read(tag_raw="")

    def strip(self, prompt: str, attempt: int) -> Read:
        """Return an empty strip read.

        Args:
            prompt: Ignored.
            attempt: Ignored.

        Returns:
            Read with nothing in it.
        """
        self.calls += 1
        return Read(counts_raw="")


def test_run_records_what_a_step_item_loop_records(adj, five_items, tmp_path):
    """run() over 5 items logs exactly what calling step_item per item logs."""
    via_run = RunLog(root=tmp_path, run_id="via-run")
    run(five_items, adj, ScriptedInput(adj), via_run)

    via_step = RunLog(root=tmp_path, run_id="via-step")
    source = ScriptedInput(adj)
    for item in five_items:
        step_item(item, adj, source, via_step, 1)

    assert recorded(via_run) == recorded(via_step)
    assert len(recorded(via_run)) == 5


def test_three_abstains_leave_three_attempts_and_a_flag(adj, five_items, tmp_path):
    """Three abstaining reads: 3 attempts, no fourth ask, and the item is flagged."""
    item = next(i for i in five_items if i.kind == "device")
    log = RunLog(root=tmp_path, run_id="abstains")
    source = SilentInput()

    run([item], adj, source, log)

    attempts = recorded(log)
    assert source.calls == 1 + MAX_REASKS          # asked once, re-asked twice
    assert [a["attempt_no"] for a in attempts] == [1, 2, 3]
    assert {a["outcome"] for a in attempts} == {ABSTAIN}
    assert [a.item for a in log.flags] == [item.tag]
