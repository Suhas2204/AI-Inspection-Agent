"""Tests for Block 4 (normalise.py): canonical forms, and misreads stay misreads."""

import pytest

from redlining.normalise import (
    DIGIT_WORDS,
    LEADING_FILLER,
    MAX_TOKEN_RUN,
    MAX_TOKENS,
    PART_LETTER_HOMOPHONES,
    PHONETIC,
    TEEN_TENS_WORDS,
    compact,
    normalise_part,
    normalise_rating,
    normalise_tag,
    runaway,
    strip_leading_filler,
)


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


# ------------------------------------------------- the repetition guard

# Verbatim from run 20260927-130613, which is why these are reconstructions
# rather than invented strings: -7F9 attempt 1 is "9, 7, " followed by "9"
# 110 more times, 334 characters in all, and -12F4 attempt 1 repeats the
# phrase "F4 minus 12" eight times. LOOP_7F9_VAD is the SAME clip decoded
# with vad_filter=True, which is the setting LocalTranscriber now uses.
LOOP_7F9 = "9, 7, " + ", ".join(["9"] * 110)
LOOP_7F9_VAD = " ".join(["9."] * 28)
LOOP_12F4 = "F4 minus 12 " * 7 + "F4"


def test_runaway_names_the_repeated_token():
    """The -7F9 loop is reported as a repeat, with the token and the count."""
    reason = runaway(LOOP_7F9, "tag")
    assert reason
    assert "repeated '9' 110 times" in reason


def test_vad_does_not_make_the_guard_redundant():
    """The same clip with vad_filter=True is shorter and still a runaway.

    This is the empirical reason the guard exists alongside VAD: Silero cut
    -7F9 from 112 tokens to 28, and 28 repetitions of "9" is still not a read.
    """
    assert runaway(LOOP_7F9_VAD, "tag")


def test_a_repeated_phrase_is_caught_by_length_not_by_the_run_test():
    """-12F4 repeats a phrase, so only the length half of the guard reaches it."""
    tokens = LOOP_12F4.lower().split()
    assert all(a != b for a, b in zip(tokens, tokens[1:])),         "no token repeats back to back, so the run test cannot catch this one"
    reason = runaway(LOOP_12F4, "tag")
    assert reason
    assert "tokens where a spoken tag needs at most" in reason


@pytest.mark.parametrize("run_length, flagged", [
    (MAX_TOKEN_RUN, False),             # 5 in a row is allowed
    (MAX_TOKEN_RUN + 1, True),          # "more than 5" is not
])
def test_the_run_limit_is_more_than_not_at_least(run_length, flagged):
    """The boundary is exactly MAX_TOKEN_RUN repeats allowed, one more flagged."""
    assert bool(runaway(" ".join(["9"] * run_length), "tag")) is flagged


@pytest.mark.parametrize("kind", sorted(MAX_TOKENS))
def test_the_budget_boundary_holds_for_every_kind(kind):
    """Each kind allows its budget in distinct tokens and flags one more."""
    words = ["one", "two", "three", "four", "five", "six", "seven", "eight",
             "nine", "ten", "eleven", "twelve", "alpha", "bravo", "charlie",
             "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet",
             "kilo", "lima", "mike"]
    budget = MAX_TOKENS[kind]
    assert not runaway(" ".join(words[:budget]), kind)
    assert runaway(" ".join(words[:budget + 1]), kind)


@pytest.mark.parametrize("raw, kind", [
    ("Minus 7F9", "tag"),               # the -7F9 re-read that was heard right
    ("minus 12 f4", "tag"),             # the -12F4 re-read
    ("minus 13 k2", "tag"),
    ("L3, N1, PE1, Bracket 1.", "counts"),
    ("a nine f zero three one one six", "part"),
    ("acti nine i c sixty n b sixteen amps", "rating"),
])
def test_one_read_transcripts_pass_the_guard(raw, kind):
    """A healthy transcript is never called a runaway, in any read kind."""
    assert runaway(raw, kind) == ""


@pytest.mark.parametrize("raw", ["", "   ", ".,;"])
def test_empty_is_not_a_runaway(raw):
    """Nothing read is a different failure with its own abstain, not this one."""
    assert runaway(raw, "tag") == ""


@pytest.mark.parametrize("normalise, kind", [
    (normalise_tag, "tag"),
    (normalise_part, "part"),
    (normalise_rating, "rating"),
])
def test_a_runaway_is_malformed_in_every_normaliser(normalise, kind):
    """The guard reaches all three normalisers, so no caller has to ask twice."""
    result = normalise(LOOP_7F9)
    assert not result.well_formed
    assert "runaway decode" in result.reason


def test_a_runaway_still_carries_its_value_and_its_raw_text():
    """Flagging a loop must not launder it away: the evidence is kept.

    The CER in experiments/block05_asr/score.py aligns .value, so emptying it
    here would silently move that metric while claiming only to classify.
    """
    result = normalise_tag(LOOP_7F9)
    assert result.raw == LOOP_7F9
    assert result.value.startswith("-97999")


def test_a_short_repeat_that_whisper_punctuates_unevenly_is_one_run():
    """Punctuation is stripped, so "9, 9. 9," is one run of three, not three."""
    reason = runaway("9, 9. 9, 9. 9, 9. 9.", "tag")
    assert "repeated '9' 7 times" in reason


# ------------------------------------------------- leading filler

def test_the_vad_on_transcript_that_motivated_this_now_normalises():
    """"So, minus 12 F3." is -12F3.

    Verbatim from the VAD comparison: switching vad_filter=True on made
    Whisper write that clip as a sentence. Before the strip it became
    "-SO12F3", failed the tag shape, and a clean read turned into an abstain.
    """
    result = normalise_tag("So, minus 12 F3.")
    assert result.value == "-12F3"
    assert result.well_formed


@pytest.mark.parametrize("raw, expected", [
    ("So, minus 12 F3.", "-12F3"),
    ("so minus 1 f1", "-1F1"),
    ("So so minus 1 f1", "-1F1"),          # a run of filler, not just one
    ("minus 1 f1", "-1F1"),                # nothing to strip
])
def test_leading_filler_does_not_reach_the_value(raw, expected):
    """Filler at the front is punctuation, whether there is one word or three."""
    assert normalise_tag(raw).value == expected


def test_filler_in_the_middle_is_still_an_error():
    """A stray word inside a read stays visible; only the FRONT is stripped.

    This is the laundering guard for LEADING_FILLER. Dropping "so" wherever
    it appeared would quietly repair "minus 12 so f3" into a legal tag, and
    a read that went wrong in the middle is exactly what must not be
    repaired (CONTEXT §7).
    """
    result = normalise_tag("minus 12 so f3")
    assert not result.well_formed
    assert result.value == "-12SOF3"


def test_a_transcript_of_nothing_but_filler_reads_as_nothing():
    """Filler only is "nothing recognised", which abstains -- not a tag."""
    result = normalise_tag("So.")
    assert not result.well_formed
    assert result.value == ""


def test_filler_is_stripped_in_every_normaliser():
    """Part and rating reads get the same treatment as tags."""
    assert normalise_part("so a nine f zero three one one six").value == "A9F03116"
    assert normalise_rating("so i c sixty n b sixteen").value == compact("iC60N B16")


def test_no_filler_word_can_also_be_content():
    """LEADING_FILLER must not overlap any vocabulary that carries meaning.

    "oh" is the reason this test exists: it is a sentence opener in English
    and a ZERO in DIGIT_WORDS, so stripping it would delete a spoken digit.
    Anything added to LEADING_FILLER has to clear this.
    """
    content = (set(DIGIT_WORDS) | set(TEEN_TENS_WORDS) | set(PHONETIC)
               | set(PART_LETTER_HOMOPHONES))
    overlap = LEADING_FILLER & content
    assert not overlap, f"{overlap} would be stripped out of a real read"


def test_strip_leading_filler_leaves_a_clean_token_list_alone():
    """The helper is a no-op on tokens that do not start with filler."""
    assert strip_leading_filler(["minus", "1", "f1"]) == ["minus", "1", "f1"]
    assert strip_leading_filler(["so", "minus", "1"]) == ["minus", "1"]
    assert strip_leading_filler(["so"]) == []
    assert strip_leading_filler([]) == []
