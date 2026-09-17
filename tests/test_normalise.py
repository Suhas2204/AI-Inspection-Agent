"""Tests for Block 4 (normalise.py): canonical forms, and misreads stay misreads."""

import pytest

from redlining.normalise import compact, normalise_part, normalise_rating, normalise_tag


@pytest.mark.parametrize("raw, expected", [
    ("a nine f zero three one one six", "A9F03116"),
    ("a nine f zero three three one zero", "A9F03310"),
    ("A9F03116", "A9F03116"),
    ("alpha nine foxtrot zero three one one six", "A9F03116"),
    ("a nine p four four six one zero", "A9P44610"),
    ("a nine f zero three double one six", "A9F03116"),
])
def test_part_numbers(raw, expected):
    """Spoken part numbers, incl. NATO letters and 'double', become canonical strings."""
    result = normalise_part(raw)
    assert result.value == expected
    assert result.well_formed


@pytest.mark.parametrize("raw, printed", [
    ("i c sixty n b sixteen", "iC60N B16"),
    ("i c forty n b ten", "iC40N B10"),
    ("i d p n n vigi b sixteen amps", "iDPN N Vigi B 16A"),
    ("acti nine i c sixty n b ten", "Acti9 iC60N B10"),
])
def test_rating_line_equals_compacted_printed_label(raw, printed):
    """A spoken rating line equals the printed label once both are compacted."""
    assert normalise_rating(raw).value == compact(printed)


@pytest.mark.parametrize("raw, expected", [
    ("Minus 5, F2", "-5F2"),
    ("minus 1q1", "-1Q1"),
    ("minus 13 k2", "-13K2"),
    ("minus 12 f6", "-12F6"),
    ("minus 5F3.", "-5F3"),
])
def test_tags_as_whisper_wrote_them(raw, expected):
    """Real tag transcripts, including Whisper's trailing punctuation."""
    result = normalise_tag(raw)
    assert result.value == expected
    assert result.well_formed


@pytest.mark.parametrize("raw, must_not_be", [
    ("a nine f zero three one one", "A9F03116"),
    ("a nine f zero three one one five", "A9F03116"),
])
def test_misreads_are_never_corrected(raw, must_not_be):
    """A short or misheard part number is never repaired into a legal value."""
    assert normalise_part(raw).value != must_not_be


def test_junk_is_marked_malformed():
    """Unrecognised speech is flagged as malformed, not guessed at."""
    assert not normalise_part("hallo wie geht es dir").well_formed


def test_deterministic():
    """The same transcript always gives the same result."""
    raw = "a nine f zero three one one six"
    assert normalise_part(raw) == normalise_part(raw)


@pytest.mark.parametrize("text, expected", [
    ("Acti9 iC60N B16", "ACTI9IC60NB16"),
    ("4Ö,63A,230VAC", "4O63A230VAC"),
    (None, ""),
])
def test_compact(text, expected):
    """compact() keeps only uppercase letters and digits, folding accents."""
    assert compact(text) == expected
