"""Tests for Block 4 (normalise.py): canonical forms, and misreads stay misreads."""

import pytest

from redlining.normalise import (
    CARRIER_PHRASES,
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
    strip_lead_in,
    strip_leading_filler,
)
from redlining.normalise import _pre


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


# ------------------------------------------------- carrier phrases

@pytest.mark.parametrize("carrier", [
    "it says", "it reads", "I see", "I read", "the tag is", "that's",
])
def test_a_carrier_phrase_normalises_to_the_same_value(carrier):
    """The reading is the reading, however the trainee introduced it."""
    bare = normalise_tag("minus 1 F1")
    carried = normalise_tag(f"{carrier} minus 1 F1")

    assert carried.value == bare.value == "-1F1"
    assert carried.well_formed == bare.well_formed is True


@pytest.mark.parametrize("carrier", [
    "it says", "it reads", "I see", "I read", "the tag is", "that's",
])
def test_what_was_stripped_is_on_the_record(carrier):
    """Nothing is removed silently: raw keeps it all, stripped names the cut.

    This is what separates a fixed strip from a model tidying a transcript.
    A reviewer can see the trainee's whole utterance, the value that was
    judged, and exactly which words sit between the two.
    """
    carried = normalise_tag(f"{carrier} minus 1 F1")

    assert carried.raw == f"{carrier} minus 1 F1"
    assert carried.stripped
    assert " ".join(carried.stripped) == " ".join(_pre(carrier))
    assert not normalise_tag("minus 1 F1").stripped


def test_a_misread_behind_a_carrier_phrase_is_still_a_misread():
    """Stripping the lead-in must not repair what follows it.

    The whole point of the fixed list is that it removes address, not
    content. "-9F9" is a real tag and the wrong one here; "minus 9 F 9 9 9"
    is not a tag at all. Neither becomes acceptable by being introduced
    politely.
    """
    wrong_tag = normalise_tag("it says minus 9 F 9")
    assert wrong_tag.value == "-9F9" == normalise_tag("minus 9 F 9").value
    assert wrong_tag.well_formed

    malformed = normalise_tag("the tag is minus 9 F 9 9 9")
    assert not malformed.well_formed
    assert malformed.value == normalise_tag("minus 9 F 9 9 9").value


def test_a_carrier_phrase_in_the_middle_is_still_an_error():
    """Leading-only, like the filler. A lead-in inside a reading is a defect."""
    result = normalise_tag("minus 1 it says F1")
    assert not result.well_formed
    assert not result.stripped


def test_a_carrier_phrase_with_no_reading_behind_it_reads_as_nothing():
    """"It says" alone is not a reading, and is not guessed at."""
    result = normalise_tag("it says")
    assert result.value == ""
    assert not result.well_formed
    assert result.stripped == ["it", "says"]


def test_filler_and_a_carrier_can_both_be_stripped():
    """A trainee can hesitate and address you in the same breath."""
    result = normalise_tag("So, it says minus 1 F1")
    assert result.value == "-1F1"
    assert result.stripped == ["so", "it", "says"]


def test_every_carrier_phrase_is_more_than_one_token():
    """The invariant that makes carriers safe where single words would not be.

    "i", "s" and "is" would each be read as content on their own -- a single
    letter normalises to a letter. They are only ever removed as part of a
    phrase, so a one-token carrier would be a bug, and this is what stops
    one being added by accident.
    """
    for phrase in CARRIER_PHRASES:
        assert len(_pre(phrase)) >= 2, phrase


def test_carrier_phrases_are_a_closed_list():
    """A phrase that is not on the list is not stripped, however similar.

    "that is" reads like "that's" and is deliberately absent: the list is
    closed, and extending it is a decision someone has to make on purpose.
    """
    result = normalise_tag("that is minus 1 f1")
    assert not result.stripped
    assert result.value != "-1F1"


def test_strip_lead_in_reports_both_halves():
    """kept and removed together account for every token given."""
    kept, removed = strip_lead_in(["it", "says", "minus", "1", "f1"])
    assert kept == ["minus", "1", "f1"]
    assert removed == ["it", "says"]

    kept, removed = strip_lead_in(["minus", "1", "f1"])
    assert kept == ["minus", "1", "f1"]
    assert removed == []


def test_strip_lead_in_keeps_the_case_it_was_given():
    """session.count_tokens passes uppercase tokens straight through."""
    kept, removed = strip_lead_in(["IT", "SAYS", "L", "3"])
    assert kept == ["L", "3"]
    assert removed == ["IT", "SAYS"]
