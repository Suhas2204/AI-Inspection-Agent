"""Tests for Block 6 (adjudicate.py): each case asserts one expected outcome.

- -8F7 is A9F03110 / C60N,1P,10A,B (a B10 among the B16s).
- -5F1 prints no part number, only its rating line.
- -X4 is used for the strip count checks.
"""

import pytest

from redlining.adjudicate import (
    ABSTAIN,
    MATCH,
    MISMATCH,
    NOT_IN_SCHEMATIC,
    Adjudicator,
)
from redlining.normalise import compact
from redlining.paths import SCHEMATIC


@pytest.fixture(scope="module")
def adj() -> Adjudicator:
    """Adjudicator loaded once per module from the cleaned schematic."""
    return Adjudicator.from_export(SCHEMATIC)


# -8F7 really is A9F03110 / C60N,1P,10A,B -- a B10 among the B16s.

def test_match_both_values(adj):
    """Correct part number and rating line -> MATCH."""
    v = adj.judge_device("-8F7", part="A9F03110", rating=compact("C60N,1P,10A,B"))
    assert v.outcome == MATCH


def test_mismatch_b16_fitted_where_b10_belongs(adj):
    """A real B16 part and rating where a B10 belongs -> MISMATCH."""
    v = adj.judge_device("-8F7", part="A9F03116", rating=compact("C60N,1P,16A,B"))
    assert v.outcome == MISMATCH


def test_not_in_schematic_foreign_part(adj):
    """A part number found nowhere in the cabinet -> NOT_IN_SCHEMATIC."""
    v = adj.judge_device("-8F7", part="XYZ99999", rating=compact("C60N,1P,10A,B"))
    assert v.outcome == NOT_IN_SCHEMATIC


def test_abstain_one_character_off_expected_value(adj):
    """Unknown part one character off the expected one -> ABSTAIN (likely misread)."""
    v = adj.judge_device("-8F7", part="A9F03115", rating=compact("C60N,1P,10A,B"))
    assert v.outcome == ABSTAIN


def test_abstain_two_values_on_label_disagree(adj):
    """Correct part but a rating line that doesn't fit it -> ABSTAIN."""
    v = adj.judge_device("-8F7", part="A9F03110", rating=compact("C60N,1P,16A,B"))
    assert v.outcome == ABSTAIN


def test_abstain_malformed_read(adj):
    """A read the normaliser marked malformed -> ABSTAIN."""
    v = adj.judge_device("-8F7", part="A9F0311", part_well_formed=False)
    assert v.outcome == ABSTAIN


def test_match_label_with_no_printed_part_number(adj):
    """Label with no printed part number: correct rating line -> MATCH."""
    v = adj.judge_device("-5F1", rating=compact("2P 16A-B/30mA, Typ A"))
    assert v.outcome == MATCH


def test_mismatch_no_part_label_reading_wrong_rating(adj):
    """Label with no printed part number: wrong rating line -> MISMATCH."""
    v = adj.judge_device("-5F1", rating=compact("2P 13A-B/30mA, Typ A"))
    assert v.outcome == MISMATCH


def test_strip_counts_correct(adj):
    """Strip counts equal to the schematic -> MATCH."""
    v = adj.judge_strip("-X4", dict(adj.expected_counts("-X4")))
    assert v.outcome == MATCH


def test_strip_counts_wrong(adj):
    """Strip counts with one N missing -> MISMATCH."""
    v = adj.judge_strip("-X4", {"N": 7, "L": 8, "PE": 8, "BRACKET": 1})
    assert v.outcome == MISMATCH


def test_all_four_outcomes_reachable(adj):
    """Four device reads together reach every possible outcome."""
    outcomes = {
        adj.judge_device("-8F7", part="A9F03110",
                         rating=compact("C60N,1P,10A,B")).outcome,
        adj.judge_device("-8F7", part="A9F03116",
                         rating=compact("C60N,1P,16A,B")).outcome,
        adj.judge_device("-8F7", part="XYZ99999",
                         rating=compact("C60N,1P,10A,B")).outcome,
        adj.judge_device("-8F7", part="A9F03115",
                         rating=compact("C60N,1P,10A,B")).outcome,
    }
    assert outcomes == {MATCH, MISMATCH, NOT_IN_SCHEMATIC, ABSTAIN}
