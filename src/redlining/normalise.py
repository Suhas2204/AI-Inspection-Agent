"""Block 4: turn a raw ASR transcript into a canonical string.

- Rules only: no model, no network, no API key. Deterministic.
- No fuzzy matching against the legal part-number set. A malformed read is
  marked malformed and passed on -- correcting it would launder the defect
  Block 9 plants (BLOCK_GUIDE Block 4, CONTEXT.md §7).
- WARNING: the word lists are a starting point. Extend them from real
  transcripts (transcripts.csv), not from imagination.

Example:
    from redlining.normalise import normalise_part, normalise_rating

    normalise_part("a nine f zero three one one six").value   # 'A9F03116'
    normalise_rating("i c sixty n b sixteen").value           # 'IC60NB16'
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

DIGIT_WORDS = {
    "zero": "0", "oh": "0", "o": "0", "nought": "0", "null": "0",
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9",
}

# Spoken as a whole number, common in rating lines: "b sixteen" -> B16
TEEN_TENS_WORDS = {
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30",
    "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70",
    "eighty": "80", "ninety": "90", "hundred": "100",
}

# NATO alphabet. HANDOFF §9 flags this as the one good idea in the external
# PDF -- worth testing in Block 5. Harmless to accept here either way.
PHONETIC = {
    "alpha": "A", "alfa": "A", "bravo": "B", "charlie": "C", "delta": "D",
    "echo": "E", "foxtrot": "F", "golf": "G", "hotel": "H", "india": "I",
    "juliet": "J", "juliett": "J", "kilo": "K", "lima": "L", "mike": "M",
    "november": "N", "oscar": "O", "papa": "P", "quebec": "Q", "romeo": "R",
    "sierra": "S", "tango": "T", "uniform": "U", "victor": "V",
    "whiskey": "W", "xray": "X", "x-ray": "X", "yankee": "Y", "zulu": "Z",
}

# Whisper writes prose. These are filler, not content.
NOISE_WORDS = {"the", "and", "a", "um", "uh", "er", "please", "okay", "ok"}

# Sentence openers, dropped only at the FRONT of a transcript. Whisper
# sometimes writes the clip as a sentence: "So, minus 12 F3." for a clip that
# says nothing but the tag. Found when vad_filter=True was switched on, which
# is where it showed up; the pre-VAD decode of that same clip was clean.
#
# Leading-only, not added to NOISE_WORDS, and this is the whole point of a
# second list: NOISE_WORDS drops its members wherever they appear, and a
# stray word in the MIDDLE of a tag read is evidence that something went
# wrong with the read. Dropping it there would launder exactly the defect
# this project measures (CONTEXT §7). At the front it is punctuation.
#
# Measured, not imagined, per the warning at the top of this module. Every
# transcript on hand was checked for a leading token that is not a digit, a
# number word or a letter -- the 73 attempts of run 20260927-130613, both
# sides of all 72 clips in the VAD comparison, and the 19 rows of
# transcripts.csv -- and "so" is the only one. Extend this from real
# transcripts when another appears, never with a word any vocabulary above
# could read as content (test_normalise.py enforces that much).
LEADING_FILLER = {"so"}

# 'a' is both an article and the letter A. In part-number mode it is a letter.
PART_LETTER_HOMOPHONES = {"a": "A", "ay": "A", "eh": "A", "be": "B", "bee": "B",
                          "see": "C", "sea": "C", "cee": "C", "dee": "D",
                          "ee": "E", "ef": "F", "eff": "F", "gee": "G",
                          "aitch": "H", "eye": "I", "jay": "J", "kay": "K",
                          "el": "L", "ell": "L", "em": "M", "en": "N",
                          "pee": "P", "pea": "P", "cue": "Q", "queue": "Q",
                          "are": "R", "ar": "R", "es": "S", "ess": "S",
                          "tee": "T", "tea": "T", "you": "U", "vee": "V",
                          "double-u": "W", "ex": "X", "why": "Y", "wye": "Y",
                          "zed": "Z", "zee": "Z"}

PART_RE = re.compile(r"^[A-Z0-9.\-]{4,20}$")

# --------------------------------------------------------------------------
# Repetition guard
# --------------------------------------------------------------------------
# Whisper at temperature=0 can fall into a loop and emit one token until the
# decode window is full. Two attempts of run 20260927-130613 did: -7F9
# attempt 1 came back as 112 tokens, 110 of them "9", and -12F4 attempt 1
# repeated the phrase "F4 minus 12" eight times. Neither is a misheard
# character -- it is the decoder failing -- and a pipeline that judges them
# anyway turns a decode failure into a finding about the cabinet.
#
# Two tests, because one does not reach both shapes: -12F4 repeated a PHRASE,
# so no token occurs twice in a row in it and the run test passes it. Only
# the length test catches that one.
MAX_TOKEN_RUN = 5           # one token more often than this, back to back

# Token budgets, per read kind. "tag" and "counts" are measured over the 68
# healthy attempts of run 20260927-130613 (tag mode): the longest device read
# is 4 tokens, the longest strip read 5, so 12 leaves well over 2x headroom
# and still sits far below both loops (22 and 112 tokens). No run has used
# part mode yet, so "part" and "rating" are not measured; they are set from
# the longest fully spelled-out read in this module's own examples ("acti nine
# i c sixty n b sixteen amps", 9 tokens) with the same headroom. Narrow them
# once part mode has a corpus. Do not widen them from imagination -- the
# whole point is that a healthy read is nowhere near the limit.
MAX_TOKENS = {"tag": 12, "counts": 12, "part": 24, "rating": 24}


@dataclass
class Normalised:
    """Result of normalising one transcript. The raw text is always kept.

    Attributes:
        raw: Original transcript (BLOCK_GUIDE: never lose it).
        value: Canonical string.
        kind: "part", "rating" or "tag".
        well_formed: Shape looks plausible -- NOT "exists in the schematic".
        reason: Why it is not well formed, if so.
        tokens: The pieces that built the value.
    """
    raw: str
    value: str
    kind: str                     # 'part' | 'rating' | 'tag'
    well_formed: bool             # shape is plausible -- NOT 'exists in schematic'
    reason: str = ""
    tokens: list[str] = field(default_factory=list)


def _pre(text: str) -> list[str]:
    """Lowercase, strip accents and punctuation, and split into tokens.

    Args:
        text: Raw transcript.

    Returns:
        List of tokens.
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("-", " ").replace("_", " ")
    text = re.sub(r"[^a-z0-9\s.+/]", " ", text)
    return [t for t in text.split() if t]


def _expand_repeats(tokens: list[str]) -> list[str]:
    """Expand "double" / "triple" into repeated tokens.

    Example: ["double", "three"] -> ["three", "three"].

    Args:
        tokens: Tokens from _pre().

    Returns:
        Tokens with repeats expanded.
    """
    out, i = [], 0
    mult = {"double": 2, "triple": 3}
    while i < len(tokens):
        if tokens[i] in mult and i + 1 < len(tokens):
            out.extend([tokens[i + 1]] * mult[tokens[i]])
            i += 2
        else:
            out.append(tokens[i])
            i += 1
    return out


def strip_leading_filler(tokens: list[str]) -> list[str]:
    """Drop sentence-opener filler from the front of a token list.

    Only the front, and only LEADING_FILLER. See that set for why the two
    restrictions matter.

    Args:
        tokens: Tokens from _pre(), or any token list. Case and trailing
            punctuation are ignored, so session.count_tokens can pass its
            uppercase tokens through unchanged.

    Returns:
        The tokens with any run of leading filler removed, in the case they
        were given in. A transcript that
        is nothing but filler comes back empty, which reads downstream as
        "nothing was read" -- the right answer for a clip with no tag in it.
    """
    first = 0
    while (first < len(tokens)
           and tokens[first].strip(".,;:!?").lower() in LEADING_FILLER):
        first += 1
    return tokens[first:]


def _longest_run(tokens: list[str]) -> tuple[str, int]:
    """Find the most-repeated token run.

    Args:
        tokens: Tokens from _pre().

    Returns:
        (token, length) of the longest back-to-back repeat; ("", 0) if empty.
    """
    if not tokens:
        return "", 0
    best_token, best, current = tokens[0], 1, 1
    for previous, token in zip(tokens, tokens[1:]):
        current = current + 1 if token == previous else 1
        if current > best:
            best_token, best = token, current
    return best_token, best


def runaway(raw: str, kind: str) -> str:
    """Name the decoder failure in a transcript, if there is one.

    This is a guard, not a repair: a transcript it names is abstained on, so
    the runner re-asks. Nothing is corrected and nothing is dropped -- the raw
    text is still logged, as everywhere else (CONTEXT §7).

    An empty transcript is NOT a runaway. "Nothing was read" is a different
    failure with its own abstain, and naming it twice would hide it here.

    Args:
        raw: Raw transcript, before normalising.
        kind: Which budget applies -- "tag", "part", "rating" or "counts".

    Returns:
        A reason to abstain, or "" if the transcript looks like one read.

    Raises:
        KeyError: If kind is not a known read kind.
    """
    budget = MAX_TOKENS[kind]            # before any work: an unknown kind is a bug
    # Punctuation is stripped as normalise_tag strips it, so that a loop
    # Whisper punctuates unevenly -- "9, 9. 9," -- is still one run and not
    # three. Without this, VAD-on's "9. 9. 9." reads as the token "9.".
    tokens = [t.strip(".,;:!?") for t in _pre(raw)]
    tokens = [t for t in tokens if t]
    if not tokens:
        return ""

    token, run = _longest_run(tokens)
    if run > MAX_TOKEN_RUN:
        return (f"the decoder repeated {token!r} {run} times in a row "
                f"(limit {MAX_TOKEN_RUN}): a runaway decode, not a read. "
                f"Ask again")
    if len(tokens) > budget:
        return (f"the transcript is {len(tokens)} tokens where a spoken "
                f"{kind} needs at most {budget}: a runaway decode, not a "
                f"read. Ask again")
    return ""


def normalise_part(raw: str) -> Normalised:
    """Turn a spoken part number into a canonical string. Never corrected to a legal value.

    Args:
        raw: Transcript, e.g. "a nine f zero three one one six".

    Returns:
        Normalised(kind="part"), e.g. value "A9F03116". well_formed is False
        for unknown tokens, nothing recognised, or an implausible shape.
    """
    tokens = strip_leading_filler(_expand_repeats(_pre(raw)))
    out: list[str] = []
    unknown: list[str] = []

    for tok in tokens:
        if tok in {"minus", "dash", "hyphen"}:
            continue                          # tag prefix, not part of the number
        if tok.isdigit():
            out.append(tok)
        elif tok in DIGIT_WORDS:
            out.append(DIGIT_WORDS[tok])
        elif tok in TEEN_TENS_WORDS:
            out.append(TEEN_TENS_WORDS[tok])
        elif tok in PHONETIC:
            out.append(PHONETIC[tok])
        elif len(tok) == 1 and tok.isalpha():
            out.append(tok.upper())
        elif tok in PART_LETTER_HOMOPHONES:
            out.append(PART_LETTER_HOMOPHONES[tok])
        elif re.fullmatch(r"[a-z0-9.\-]+", tok) and any(c.isdigit() for c in tok):
            # Already merged. Dots and hyphens occur in real part numbers
            # here: '104013.SK', 'NR12-001-3x230V', 'EPS-T2/3+1-275-FM'.
            out.append(tok.upper())
        elif tok in NOISE_WORDS:
            continue
        else:
            unknown.append(tok)

    value = "".join(out)

    stuck = runaway(raw, "part")
    if stuck:
        return Normalised(raw, value, "part", False, stuck, out)

    if unknown:
        return Normalised(raw, value, "part", False,
                          f"unrecognised token(s): {', '.join(unknown)}", out)
    if not value:
        return Normalised(raw, "", "part", False, "nothing recognised", out)
    if not PART_RE.fullmatch(value):
        return Normalised(raw, value, "part", False,
                          f"shape implausible for a part number: {value!r}", out)
    return Normalised(raw, value, "part", True, "", out)


def normalise_rating(raw: str) -> Normalised:
    """Turn a spoken rating line into a compact canonical string, e.g. "IC60NB16".

    Spaces are removed on purpose: splitting "IC60N" from "B16" would need the
    legal set, which is the adjudicator's job. Block 6 compacts the schematic
    side the same way, so both sides stay comparable.

    Args:
        raw: Transcript, e.g. "i c sixty n b sixteen".

    Returns:
        Normalised(kind="rating"). well_formed is False for unknown tokens or
        nothing recognised.
    """
    tokens = strip_leading_filler(_expand_repeats(_pre(raw)))
    out: list[str] = []
    unknown: list[str] = []

    for tok in tokens:
        if tok in {"minus", "dash", "hyphen"}:
            continue
        if tok in {"amp", "amps", "ampere", "amperes"}:
            out.append("A")               # trailing unit, as printed: 'B 16A'
        elif tok.isdigit():
            out.append(tok)
        elif tok in DIGIT_WORDS:
            out.append(DIGIT_WORDS[tok])
        elif tok in TEEN_TENS_WORDS:
            out.append(TEEN_TENS_WORDS[tok])
        elif tok in PHONETIC:
            out.append(PHONETIC[tok])
        elif re.fullmatch(r"[a-z0-9+/.]+", tok):
            out.append(tok.upper())
        elif tok in NOISE_WORDS:
            continue
        else:
            unknown.append(tok)

    value = "".join(out)

    stuck = runaway(raw, "rating")
    if stuck:
        return Normalised(raw, value, "rating", False, stuck, out)

    if unknown:
        return Normalised(raw, value, "rating", False,
                          f"unrecognised token(s): {', '.join(unknown)}", out)
    if not value:
        return Normalised(raw, "", "rating", False, "nothing recognised", out)
    return Normalised(raw, value, "rating", True, "", out)


def normalise_tag(raw: str) -> Normalised:
    """Turn a spoken device tag into canonical form: "Minus 5, F2" -> "-5F2".

    Only canonicalises; never snaps to the legal tag set (CONTEXT §7).
    Membership is the adjudicator's call.

    Args:
        raw: Transcript, e.g. "minus 13 k2".

    Returns:
        Normalised(kind="tag"). well_formed is False for unknown tokens,
        nothing recognised, or a shape unlike "-10F1" / "-D1".
    """
    # Whisper punctuates: 'minus 5F3.' arrives with the stop attached to the
    # token. Found in the first live run, 31 Aug -- it cost 2 of 10 items.
    tokens = [t.strip(".,;:!?") for t in _expand_repeats(_pre(raw))]
    tokens = strip_leading_filler([t for t in tokens if t])
    out: list[str] = []
    unknown: list[str] = []

    for tok in tokens:
        if tok in {"minus", "dash", "hyphen", "negative"}:
            continue                      # the leading '-' is added at the end
        if tok.isdigit():
            out.append(tok)
        elif tok in DIGIT_WORDS:
            out.append(DIGIT_WORDS[tok])
        elif tok in TEEN_TENS_WORDS:
            out.append(TEEN_TENS_WORDS[tok])
        elif tok in PHONETIC:
            out.append(PHONETIC[tok])
        elif len(tok) == 1 and tok.isalpha():
            out.append(tok.upper())
        elif re.fullmatch(r"[a-z0-9]+", tok):
            out.append(tok.upper())       # already merged, e.g. '1q1'
        elif tok in NOISE_WORDS:
            continue
        else:
            unknown.append(tok)

    body = "".join(out)
    value = f"-{body}" if body else ""

    stuck = runaway(raw, "tag")
    if stuck:
        return Normalised(raw, value, "tag", False, stuck, out)

    if unknown:
        return Normalised(raw, value, "tag", False,
                          f"unrecognised token(s): {', '.join(unknown)}", out)
    if not body:
        return Normalised(raw, "", "tag", False, "nothing recognised", out)
    # Both real shapes in this cabinet: '-10F1' (62 tags) and '-D1' (38 tags).
    # Strip tags '-X1'..'-X8' fall under the second.
    if not re.fullmatch(r"-[0-9]{1,2}[A-Z]{1,2}[0-9]{1,2}|-[A-Z]{1,2}[0-9]{1,3}",
                        value):
        return Normalised(raw, value, "tag", False,
                          f"shape implausible for a tag: {value!r}", out)
    return Normalised(raw, value, "tag", True, "", out)


def compact(text: str) -> str:
    """THE canonical form, used on both sides of every comparison.

    Speech and schematic both go through this one function. Defining it twice
    is how the umlaut bug got in.

    Examples:
        'Acti9 iC60N B16' -> 'ACTI9IC60NB16'
        '4Ö,63A,230VAC'   -> '4O63A230VAC'   (accents folded, not dropped)

    Args:
        text: Any string, or None.

    Returns:
        Uppercase letters and digits only.
    """
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^A-Z0-9]", "", text.upper())


if __name__ == "__main__":
    cases_part = [
        ("a nine f zero three one one six", "A9F03116"),
        ("a nine f zero three three one zero", "A9F03310"),
        ("A9F03116", "A9F03116"),
        ("alpha nine foxtrot zero three one one six", "A9F03116"),
        ("a nine p four four six one zero", "A9P44610"),
        ("a nine f zero three double one six", "A9F03116"),
    ]
    cases_rating = [
        ("i c sixty n b sixteen", compact("iC60N B16")),
        ("i c forty n b ten", compact("iC40N B10")),
        ("i d p n n vigi b sixteen amps", compact("iDPN N Vigi B 16A")),
        ("acti nine i c sixty n b ten", compact("Acti9 iC60N B10")),
    ]

    fails = 0
    for raw, want in cases_part:
        got = normalise_part(raw)
        ok = got.value == want
        fails += not ok
        print(f"{'ok ' if ok else 'FAIL'} part   {raw!r:48} -> {got.value!r} {got.reason}")
    for raw, want in cases_rating:
        got = normalise_rating(raw)
        ok = got.value == want
        fails += not ok
        print(f"{'ok ' if ok else 'FAIL'} rating {raw!r:48} -> {got.value!r} (want {want!r}) {got.reason}")

    print()
    # Laundering guards. A broken read must stay broken.
    for raw, must_not_be in [
        ("a nine f zero three one one", "A9F03116"),   # one digit short
        ("a nine f zero three one one five", "A9F03116"),  # last digit misheard
    ]:
        got = normalise_part(raw)
        status = "ok " if got.value != must_not_be else "FAIL"
        print(f"{status} guard  {raw!r:48} -> {got.value!r} (must not become {must_not_be})")

    # Determinism.
    a = normalise_part("a nine f zero three one one six").value
    b = normalise_part("a nine f zero three one one six").value
    print(f"{'ok ' if a == b else 'FAIL'} deterministic")

    # A junk read must not crash.
    j = normalise_part("hallo wie geht es dir")
    print(f"{'ok ' if not j.well_formed else 'FAIL'} junk   -> well_formed={j.well_formed}: {j.reason}")

    print(f"\n{fails} failing case(s)")