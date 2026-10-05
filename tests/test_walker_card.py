"""Tests for Block 9 (walker_card.py): the two card versions, and the tell.

v1 is the card run 20260927-130613 was walked with and must stay
reproducible line for line. v2 exists because v1's strip lines leaked the
fault set: an unfaulted strip printed its tag, a faulted one printed a
sentence, so 2 of 8 strips were visibly different without reading a word.

These tests fix both halves: that v1 has not moved, and that v2's strip
lines are indistinguishable in form.
"""

import pytest

from redlining.checklist import load_checklist
from redlining.paths import DECISIONS, ROOT
from redlining.walker_card import (
    CURRENT_VERSION,
    STRIP_STEM,
    VERSIONS,
    card,
    load_overrides,
)

CARD_V1 = ROOT / "walker_card.txt"
CARD_V2 = ROOT / "walker_card_v2.txt"


@pytest.fixture(scope="module")
def items() -> list:
    """The checklist, in the order session.py prompts."""
    return load_checklist()


@pytest.fixture(scope="module")
def override() -> dict:
    """The current fault set's card overwrites."""
    return load_overrides(DECISIONS / "faults.csv")


def strip_says(lines: list[str], items: list) -> dict:
    """What each strip's instruction column says, per card line.

    Split on the strip's own "(N terminals)" detail rather than on a column
    offset, so a change to the column widths cannot make these tests pass by
    reading the wrong half of the line.

    Args:
        lines: Rendered card lines.
        items: Checklist items, to know which tags are strips.

    Returns:
        {tag: the text after the position column}.
    """
    out = {}
    for item in items:
        if item.kind != "strip":
            continue
        marker = f"({item.detail})"
        for line in lines:
            if f"strip {item.tag.lstrip('-')} " in line and marker in line:
                out[item.tag] = line.split(marker, 1)[1].strip()
    return out


def test_v1_still_reproduces_the_card_that_was_walked(items, override):
    """v1 matches walker_card.txt line for line; run 20260927-130613 read it."""
    printed = CARD_V1.read_text(encoding="utf-8").splitlines()
    rebuilt = card(items, override, version=1)
    assert len(rebuilt) == len(printed)
    assert [line.rstrip() for line in rebuilt] == [line.rstrip()
                                                   for line in printed]


def test_v2_matches_the_v2_file_on_disk(items, override):
    """walker_card_v2.txt is what version 2 renders, so the printed card is it."""
    printed = CARD_V2.read_text(encoding="utf-8").splitlines()
    rebuilt = card(items, override, version=2)
    assert [line.rstrip() for line in rebuilt] == [line.rstrip()
                                                   for line in printed]


def test_v1_leaks_the_faulted_strips(items, override):
    """The defect v2 fixes, fixed in a test so it cannot be argued about.

    In v1 a strip's column holds either a tag or a sentence, and the ones
    holding a sentence are exactly the faulted strips.
    """
    says = strip_says(card(items, override, version=1), items)
    sentences = {tag for tag, text in says.items() if " " in text}
    faulted = {i.tag for i in items
               if i.kind == "strip" and i.tag in override}

    assert sentences == faulted
    assert len(sentences) == 2, "two strip faults in the current set"


def test_v2_opens_every_strip_line_the_same_way(items, override):
    """No strip can be picked out by the form of its instruction."""
    says = strip_says(card(items, override, version=2), items)
    assert len(says) == 8, "all eight strips found on the card"
    assert all(text.startswith(STRIP_STEM) for text in says.values())
    openings = {text[:len(STRIP_STEM)] for text in says.values()}
    assert openings == {STRIP_STEM}


def test_v2_still_tells_a_faulted_strip_what_to_do(items, override):
    """Uniform wording must not swallow the fault: it is how it gets planted."""
    says = strip_says(card(items, override, version=2), items)
    for tag, instruction in override.items():
        if tag in says:
            # The fault's own words survive after the shared stem.
            tail = instruction[len("count "):] if instruction.startswith(
                "count ") else instruction
            assert tail in says[tag]


def test_v2_says_nothing_about_a_tag_at_a_strip(items, override):
    """v1 told the walker to speak "-X1" at a strip; the app asks for counts."""
    says = strip_says(card(items, override, version=2), items)
    for tag, text in says.items():
        assert tag not in text


def test_the_two_versions_differ_only_at_the_strips(items, override):
    """Every device line is identical, so v2 changes nothing already measured."""
    v1 = card(items, override, version=1)
    v2 = card(items, override, version=2)
    assert len(v1) == len(v2)

    strips = [i.tag for i in items if i.kind == "strip"]
    # The title, the how-to line and the column heading are allowed to differ:
    # v2 marks its version and renames the column. Nothing else may.
    preamble = v1[:4]
    for a, b in zip(v1, v2):
        if a.rstrip() == b.rstrip() or a in preamble:
            continue
        assert any(f"strip {t.lstrip('-')} " in a for t in strips),             f"v2 changed a line that is not a strip: {a!r}"


def test_current_version_is_two():
    """A new run should be walked with v2; v1 is kept for the old one."""
    assert CURRENT_VERSION == 2
    assert set(VERSIONS) == {1, 2}


def test_an_unknown_version_stops_the_card(items, override):
    """A typo'd version prints nothing rather than guessing a layout."""
    with pytest.raises(SystemExit):
        card(items, override, version=3)


def test_v2_refuses_a_strip_fault_written_as_a_tag(items, override):
    """A strip fault that says "speak -X9" has no uniform counting form.

    v2 stops rather than print "count the terminals, -X9", which would be a
    line that quietly says the wrong thing -- what this module refuses to do.
    """
    bad = dict(override)
    bad["-X1"] = "-X9"
    with pytest.raises(SystemExit):
        card(items, bad, version=2)
    # v1 renders it, because v1's strip column is a speak column.
    assert card(items, bad, version=1)
