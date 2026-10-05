"""Tests for Block 7 (session.py): the strip-count parser and the run loop."""

import json

import pytest

from redlining.adjudicate import ABSTAIN, MISMATCH, Adjudicator
from redlining.checklist import load_checklist
from redlining.paths import SCHEMATIC
from redlining.report import RunLog
from redlining.session import (
    MAX_REASKS,
    Read,
    ScriptedInput,
    parse_counts,
    run,
    runaway_reason,
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


# ------------------------------------------------- the repetition guard

# -7F9 attempt 1 of run 20260927-130613, verbatim: "9, 7, " and then "9"
# 110 more times. See tests/test_normalise.py for the guard's own unit tests;
# what is tested here is that it reaches the runner and stops the verdict.
LOOP_7F9 = "9, 7, " + ", ".join(["9"] * 110)


class LoopingInput:
    """Input that returns the -7F9 runaway decode, every time it is asked.

    It counts its calls, which is how the test sees how often it was asked.
    """

    _tag = ""

    def __init__(self, counts_raw: str = ""):
        """Start with no calls recorded.

        Args:
            counts_raw: What .strip() returns; defaults to the device loop,
                repeated as a counts transcript.
        """
        self.calls = 0
        self.counts_raw = counts_raw or LOOP_7F9

    def device(self, prompt: str, attempt: int) -> Read:
        """Return the runaway transcript as a device read.

        Args:
            prompt: Ignored.
            attempt: Ignored.

        Returns:
            Read whose tag_raw is the looped decode.
        """
        self.calls += 1
        return Read(tag_raw=LOOP_7F9)

    def strip(self, prompt: str, attempt: int) -> Read:
        """Return the runaway transcript as a counts read.

        Args:
            prompt: Ignored.
            attempt: Ignored.

        Returns:
            Read whose counts_raw is the looped decode.
        """
        self.calls += 1
        return Read(counts_raw=self.counts_raw)


def test_runaway_reason_reads_whichever_field_the_mode_filled():
    """Each raw field is guarded with its own budget; an empty Read is clean."""
    assert runaway_reason(Read()) == ""
    assert runaway_reason(Read(tag_raw="Minus 7F9")) == ""
    assert runaway_reason(Read(tag_raw=LOOP_7F9))
    assert runaway_reason(Read(counts_raw=LOOP_7F9))
    assert runaway_reason(Read(part_raw=LOOP_7F9))


def test_the_7f9_loop_abstains_instead_of_being_judged(adj, five_items,
                                                       tmp_path):
    """The real -7F9 runaway gives ABSTAIN, naming the loop, and no verdict."""
    item = next(i for i in five_items if i.kind == "device")
    log = RunLog(root=tmp_path, run_id="loop-device")

    verdict = step_item(item, adj, LoopingInput(), log, 1)

    assert verdict.outcome == ABSTAIN
    assert "repeated '9' 110 times" in verdict.reason
    # An empty expected would mean "no such item in the schematic", which is
    # not what happened here: the position exists and was never read.
    assert verdict.expected == {"tag": item.tag}
    assert verdict.read == {"raw": LOOP_7F9}


def test_the_7f9_loop_keeps_its_raw_text_in_the_log(adj, five_items, tmp_path):
    """An abstained loop is logged in full: the audio behind a flag is replayable."""
    item = next(i for i in five_items if i.kind == "device")
    log = RunLog(root=tmp_path, run_id="loop-logged")

    step_item(item, adj, LoopingInput(), log, 1)

    attempt, = recorded(log)
    assert attempt["raw_transcript"] == LOOP_7F9
    assert attempt["well_formed"] is False
    assert attempt["outcome"] == ABSTAIN


def test_the_7f9_loop_spends_its_re_asks_like_any_abstain(adj, five_items,
                                                          tmp_path):
    """A looping source is re-asked twice, then flagged -- the run never stops."""
    item = next(i for i in five_items if i.kind == "device")
    log = RunLog(root=tmp_path, run_id="loop-reasks")
    source = LoopingInput()

    run([item], adj, source, log)

    assert source.calls == 1 + MAX_REASKS
    assert [a["attempt_no"] for a in recorded(log)] == [1, 2, 3]
    assert {a["outcome"] for a in recorded(log)} == {ABSTAIN}
    assert len(log.flags) == 1


def test_a_looped_counts_read_does_not_become_a_mismatch(adj, tmp_path):
    """The guard covers the strip path, which has no well_formed to carry it.

    Without it this read is judged: parse_counts picks "L 3" out of the loop,
    the other functions read 0, and a decoder failure is published as a
    mismatch against the cabinet -- a finding about hardware that nobody
    looked at.
    """
    item = next(i for i in load_checklist() if i.kind == "strip")
    looped = " ".join(["L 3"] * 14)
    assert parse_counts(looped) == {"L": 3}, "the parser reads it as a count"
    assert adj.judge_strip(item.tag, parse_counts(looped)).outcome == MISMATCH

    log = RunLog(root=tmp_path, run_id="loop-strip")
    verdict = step_item(item, adj, LoopingInput(counts_raw=looped), log, 1)

    assert verdict.outcome == ABSTAIN
    assert "runaway decode" in verdict.reason
