"""Cases moved from adjudicate.py's __main__ demo block.

Same fixture cabinet (-8F7, -5F1, -X4), same reads, same expected outcomes --
just as pytest functions instead of a printed script.
"""

from pathlib import Path

import pytest

from redlining.adjudicate import (
    ABSTAIN,
    MATCH,
    MISMATCH,
    NOT_IN_SCHEMATIC,
    Adjudicator,
)
from redlining.normalise import compact

SCHEMATIC = Path(__file__).resolve().parent.parent / "data" / "schematic.cleaned.json"


@pytest.fixture(scope="module")
def adj() -> Adjudicator:
    return Adjudicator.from_export(SCHEMATIC)


# -8F7 really is A9F03110 / C60N,1P,10A,B -- a B10 among the B16s.

def test_match_both_values(adj):
    v = adj.judge_device("-8F7", part="A9F03110", rating=compact("C60N,1P,10A,B"))
    assert v.outcome == MATCH


def test_mismatch_b16_fitted_where_b10_belongs(adj):
    v = adj.judge_device("-8F7", part="A9F03116", rating=compact("C60N,1P,16A,B"))
    assert v.outcome == MISMATCH


def test_not_in_schematic_foreign_part(adj):
    v = adj.judge_device("-8F7", part="XYZ99999", rating=compact("C60N,1P,10A,B"))
    assert v.outcome == NOT_IN_SCHEMATIC


def test_abstain_one_character_off_expected_value(adj):
    v = adj.judge_device("-8F7", part="A9F03115", rating=compact("C60N,1P,10A,B"))
    assert v.outcome == ABSTAIN


def test_abstain_two_values_on_label_disagree(adj):
    v = adj.judge_device("-8F7", part="A9F03110", rating=compact("C60N,1P,16A,B"))
    assert v.outcome == ABSTAIN


def test_abstain_malformed_read(adj):
    v = adj.judge_device("-8F7", part="A9F0311", part_well_formed=False)
    assert v.outcome == ABSTAIN


def test_match_label_with_no_printed_part_number(adj):
    v = adj.judge_device("-5F1", rating=compact("2P 16A-B/30mA, Typ A"))
    assert v.outcome == MATCH


def test_mismatch_no_part_label_reading_wrong_rating(adj):
    v = adj.judge_device("-5F1", rating=compact("2P 13A-B/30mA, Typ A"))
    assert v.outcome == MISMATCH


def test_strip_counts_correct(adj):
    v = adj.judge_strip("-X4", dict(adj.expected_counts("-X4")))
    assert v.outcome == MATCH


def test_strip_counts_wrong(adj):
    v = adj.judge_strip("-X4", {"N": 7, "L": 8, "PE": 8, "BRACKET": 1})
    assert v.outcome == MISMATCH


def test_all_four_outcomes_reachable(adj):
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
