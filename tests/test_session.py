"""Tests for Block 7's strip-count parser (session.parse_counts)."""

import pytest

from redlining.session import parse_counts


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
