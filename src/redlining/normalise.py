"""Block 4: turn a raw ASR transcript into a canonical string.

Rules only. No model, no network, no API key, no fuzzy matching against the
legal part-number set. If a read comes out malformed, this module says so and
hands the malformed string onward -- correcting it here would launder exactly
the defect Block 9 plants. See BLOCK_GUIDE Block 4, and CONTEXT.md §7.

Deterministic: same input, same output, always.

    from redlining.normalise import normalise_part, normalise_rating

    normalise_part("a nine f zero three one one six").value   # 'A9F03116'
    normalise_rating("i c sixty n b sixteen").value           # 'IC60N B16'

WARNING -- the word lists below are a starting point, not a finished module.
BLOCK_GUIDE says to build these rules from your own recordings. Until 20 real
part-number reads exist, every entry here is a guess about how speech comes out.
Extend from transcripts.csv, not from imagination.
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


@dataclass
class Normalised:
    """Raw is always kept. BLOCK_GUIDE: never lose the original transcript."""
    raw: str
    value: str
    kind: str                     # 'part' | 'rating'
    well_formed: bool             # shape is plausible -- NOT 'exists in schematic'
    reason: str = ""
    tokens: list[str] = field(default_factory=list)


def _pre(text: str) -> list[str]:
    """Lowercase, strip accents and punctuation, split into tokens."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("-", " ").replace("_", " ")
    text = re.sub(r"[^a-z0-9\s.+/]", " ", text)
    return [t for t in text.split() if t]


def _expand_repeats(tokens: list[str]) -> list[str]:
    """'double three' -> '3','3'  ·  'triple zero' -> '0','0','0'."""
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


def normalise_part(raw: str) -> Normalised:
    """Spoken part number -> canonical string. Never corrected to a legal value."""
    tokens = _expand_repeats(_pre(raw))
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
    """Spoken rating line -> compact canonical string, e.g. 'IC60NB16'.

    Canonical form is uppercase alphanumeric with all spaces removed. This is
    deliberate: deciding where the family name ends and the rating begins
    ('IC60N' + 'B16') would require consulting the legal set, and that is the
    adjudicator's job, not this module's. Block 6 compacts the schematic side
    the same way, so the comparison stays honest on both sides.
    """
    tokens = _expand_repeats(_pre(raw))
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

    if unknown:
        return Normalised(raw, value, "rating", False,
                          f"unrecognised token(s): {', '.join(unknown)}", out)
    if not value:
        return Normalised(raw, "", "rating", False, "nothing recognised", out)
    return Normalised(raw, value, "rating", True, "", out)


def normalise_tag(raw: str) -> Normalised:
    """Spoken device tag -> canonical form. 'Minus 5, F2' -> '-5F2'.

    Tags are the one place CONTEXT §7 allows a closed vocabulary, because the
    schematic enumerates every legal value. This function still does not snap
    to that set -- it only canonicalises. Membership is the adjudicator's call.

    Built from real transcripts (Block 5, 28 Aug): faster-whisper emitted
    'Minus 5, F2', 'minus 1q1', 'minus 13 k2', 'minus 12 f6'.
    """
    tokens = _expand_repeats(_pre(raw))
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
    """THE canonical form. Both sides of every comparison go through this one
    function -- speech and schematic alike. Defining it twice is how the
    umlaut bug got in: '4O..' from speech never equalled '4..' from the file.

    'Acti9 iC60N B16'   -> 'ACTI9IC60NB16'
    '4Oe,63A,230VAC'    -> '4O63A230VAC'   (accents folded, not dropped)
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