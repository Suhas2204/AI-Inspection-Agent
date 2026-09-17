"""Block 6: decide whether a read agrees with the schematic.

- Input: normalised strings only. No audio, no network, no model.
- Output: a Verdict with exactly one of four outcomes plus a reason:
    match             the read is what the schematic expects here
    mismatch          a different real part -- a wrong part fitted
    not_in_schematic  names nothing in this cabinet -- probably misheard
    abstain           not enough to decide; the runner re-asks
- Key rule (CONTEXT.md §7, BLOCK_GUIDE Block 6): an unknown part number NEVER
  becomes its nearest legal neighbour. Edit distance explains an abstain; it
  never repairs a read.

Example:
    from redlining.adjudicate import Adjudicator
    adj = Adjudicator.from_export("data/processed/schematic.cleaned.json")
    adj.judge_device("-8F7", part="A9F03110", rating="C60N1P10AB")
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

MATCH = "match"
MISMATCH = "mismatch"
NOT_IN_SCHEMATIC = "not_in_schematic"
ABSTAIN = "abstain"

STRIP_TAGS = ["-X1", "-X2", "-X3", "-X4", "-X5", "-X6", "-X7", "-X8"]

# Devices whose label carries no part number. Verified at the cabinet 28 Aug:
# -5F1, -5F2, -5F3, -6F1 print only 'iDPN N Vigi B 16A' / 'B 13A'.
# For these the rating line is the only available read, so the two-value
# cross-check does not apply and a part-only mismatch is not reachable.
NO_PRINTED_PART = {"A9D56616", "A9D56613"}

# End brackets. CONTEXT §10 still lists their status as OPEN. Flip this and
# the expected strip counts change -- so the decision must be made, not drifted
# into. Block 3 owns it.
END_BRACKET_TYPE = "ZEW 35 DBS"
COUNT_END_BRACKETS = True

# Terminal function, derived from the type string per CONTEXT §7.
def terminal_functions(type_str: str) -> Counter:
    """Count the terminal functions encoded in a terminal type string.

    Args:
        type_str: Terminal type, e.g. "AITB 2.5 BB N-L-PE MC" or "WPE 35N".

    Returns:
        Counter of functions, e.g. {"N": 1, "L": 1, "PE": 1}. "ZEW" end
        brackets count as "BRACKET"; unrecognised types as "UNKNOWN".
    """
    t = type_str.upper()
    if t.startswith("WPE"):
        return Counter({"PE": 1})
    if t.startswith("WNT"):
        return Counter({"N": 1})
    if t.startswith("WDU"):
        return Counter({"L": 1})
    if t.startswith("ZEW"):
        return Counter({"BRACKET": 1})
    m = re.search(r"BB\s+([A-Z\-]+)\s+MC", t)
    if m:
        parts = [p for p in m.group(1).split("-") if p]
        # NDT = N with a disconnect link. It is an N, not an L. Confirmed
        # against the -X5 photograph: those blocks carry N markers.
        return Counter("N" if p == "NDT" else p for p in parts)
    return Counter({"UNKNOWN": 1})


# One canonical form for the whole project. Do not redefine it here.
try:
    from .normalise import compact
    from .paths import SCHEMATIC
except ImportError:                       # running the file directly
    from normalise import compact
    from paths import SCHEMATIC


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance between two strings.

    Args:
        a: First string.
        b: Second string.

    Returns:
        Minimum number of single-character inserts, deletes or substitutions.
    """
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


@dataclass
class Verdict:
    """The adjudicator's decision on one item.

    Attributes:
        outcome: One of MATCH, MISMATCH, NOT_IN_SCHEMATIC, ABSTAIN.
        reason: Plain-language explanation a reviewer can act on.
        item: The tag that was judged.
        read: What was read (normalised values).
        expected: What the schematic expects (empty for unknown items).
    """
    outcome: str
    reason: str
    item: str
    read: dict = field(default_factory=dict)
    expected: dict = field(default_factory=dict)

    def __repr__(self) -> str:
        """Short form: <outcome item: reason>."""
        return f"<{self.outcome} {self.item}: {self.reason}>"


class Adjudicator:
    """Judges device, tag and strip reads against one cabinet's schematic.

    Attributes:
        devices: Tag -> component record, for everything that is not a strip.
        terminals: Component records belonging to strips -X1..-X8.
        legal_parts: Every compacted part number in the cabinet (membership only).
    """

    def __init__(self, components: list[dict]):
        """Index the cleaned components.

        Args:
            components: The "components" list from the cleaned schematic export.
        """
        strips = set(STRIP_TAGS)
        self.devices = {r["designation"]: r for r in components
                        if r["designation"] not in strips}
        self.terminals = [r for r in components if r["designation"] in strips]
        # The legal set. Membership only -- never a target to snap to.
        self.legal_parts = {compact(r["order_reference"]) for r in components
                            if r.get("order_reference")}

    @classmethod
    def from_export(cls, path: str | Path) -> "Adjudicator":
        """Build an Adjudicator from a cleaned schematic JSON file.

        Args:
            path: Path to e.g. data/processed/schematic.cleaned.json.

        Returns:
            A ready Adjudicator.
        """
        with open(path, encoding="utf-8") as fh:
            return cls(json.load(fh)["components"])

    # ---------------------------------------------------------------- devices
    def judge_device(self, tag: str, part: str | None = None,
                     rating: str | None = None,
                     part_well_formed: bool = True,
                     rating_well_formed: bool = True) -> Verdict:
        """Judge a device read (part number and/or rating line).

        Check order: unknown tag -> nothing read -> malformed -> label with no
        printed part -> part not in cabinet -> part vs rating cross-check.

        Args:
            tag: Device tag, e.g. "-8F7".
            part: Normalised part number that was read, or None.
            rating: Normalised rating line that was read, or None.
            part_well_formed: False if the normaliser rejected the part's shape.
            rating_well_formed: False if the normaliser rejected the rating's shape.

        Returns:
            Verdict with one of the four outcomes.
        """
        rec = self.devices.get(tag)
        if rec is None:
            return Verdict(ABSTAIN, f"no device {tag} in the schematic", tag)

        exp_part = compact(rec["order_reference"])
        exp_rating = compact(rec["type"])
        expected = {"part": exp_part, "rating": exp_rating, "tag": tag}
        read = {"part": compact(part), "rating": compact(rating)}
        part, rating = read["part"], read["rating"]

        label_has_no_part = exp_part in {compact(p) for p in NO_PRINTED_PART}

        if not part and not rating:
            return Verdict(ABSTAIN, "nothing was read", tag, read, expected)

        if not part_well_formed or not rating_well_formed:
            return Verdict(ABSTAIN, "the read was malformed; ask again",
                           tag, read, expected)

        # Devices with no printed part number: the rating line is all there is.
        if label_has_no_part:
            if not rating:
                return Verdict(ABSTAIN,
                               "this label prints no part number and no rating "
                               "line was read", tag, read, expected)
            if rating == exp_rating:
                return Verdict(MATCH, "rating line matches; this label carries "
                               "no part number to cross-check", tag, read, expected)
            return Verdict(MISMATCH,
                           f"rating line reads {rating}, schematic expects "
                           f"{exp_rating}", tag, read, expected)

        # Normal path. Order matters: the legal-set question is asked FIRST.
        # If the cross-check ran first, a foreign part read alongside a correct
        # rating line would come back "the two values disagree" and the more
        # informative not-in-schematic verdict would never be reachable.
        part_ok = part == exp_part
        rating_ok = rating == exp_rating

        if part:
            if part not in self.legal_parts:
                d = edit_distance(part, exp_part)
                if d <= 2:
                    # Close to what was expected. A misread and a genuinely
                    # foreign part look identical here, so we do not choose.
                    # We name what it is near; we never adopt it.
                    return Verdict(ABSTAIN,
                                   f"{part} is in no schematic entry but differs "
                                   f"from the expected {exp_part} by {d} "
                                   f"character(s); likely a misread. Ask again",
                                   tag, read, expected)
                return Verdict(NOT_IN_SCHEMATIC,
                               f"{part} appears nowhere in this cabinet",
                               tag, read, expected)

            # The part is real. Now the two values are cross-checked.
            if rating:
                if part_ok and rating_ok:
                    return Verdict(MATCH, "part number and rating line both "
                                   "agree with the schematic", tag, read, expected)
                if part_ok != rating_ok:
                    bad = "part number" if rating_ok else "rating line"
                    return Verdict(ABSTAIN,
                                   f"the two values on one label disagree: the "
                                   f"{bad} does not fit the other; ask again",
                                   tag, read, expected)
                # Both wrong. If they agree with each other on some other real
                # device, that is a wrong part fitted -- not a misread.
                consistent = any(compact(r["order_reference"]) == part
                                 and compact(r["type"]) == rating
                                 for r in self.devices.values())
                if consistent:
                    return Verdict(MISMATCH,
                                   f"reads {part} / {rating}, schematic expects "
                                   f"{exp_part} / {exp_rating}; both values agree "
                                   f"with each other, so the fitted part is wrong",
                                   tag, read, expected)
                return Verdict(ABSTAIN,
                               f"reads {part} / {rating}; neither matches the "
                               f"expected {exp_part} / {exp_rating} and they do "
                               f"not agree with each other. Ask again",
                               tag, read, expected)

            # Part only, no rating line read.
            if part_ok:
                return Verdict(MATCH, "part number agrees with the schematic; "
                               "no rating line was read", tag, read, expected)
            return Verdict(MISMATCH,
                           f"reads {part}, schematic expects {exp_part}; {part} "
                           f"is a real part fitted elsewhere in this cabinet",
                           tag, read, expected)

        # Rating line only.
        if rating_ok:
            return Verdict(MATCH, "rating line agrees; no part number was read",
                           tag, read, expected)
        return Verdict(MISMATCH,
                       f"rating line reads {rating}, schematic expects "
                       f"{exp_rating}", tag, read, expected)

    def judge_tag(self, tag: str, read_tag: str | None,
                  well_formed: bool = True) -> Verdict:
        """Judge a spoken tag against the tag expected at this location.

        Limit: confirms right place + right label only. It cannot detect a
        wrong part fitted under a correct label (the tag doesn't change).

        Args:
            tag: Tag expected at this location, e.g. "-8F7".
            read_tag: Normalised tag that was read, or None.
            well_formed: False if the normaliser rejected the tag's shape.

        Returns:
            Verdict: MATCH; MISMATCH (a real tag from elsewhere); ABSTAIN
            (nothing read, malformed, or 1 character off); NOT_IN_SCHEMATIC.
        """
        expected = {"tag": tag}
        read = {"tag": (read_tag or "").upper()}
        got = read["tag"]

        if not got:
            return Verdict(ABSTAIN, "nothing was read", tag, read, expected)
        if not well_formed:
            return Verdict(ABSTAIN, "the read was malformed; ask again",
                           tag, read, expected)
        if got == tag.upper():
            return Verdict(MATCH, "tag matches the schematic at this location",
                           tag, read, expected)

        known = {t.upper() for t in self.devices} | {t.upper() for t in STRIP_TAGS}
        if got in known:
            return Verdict(MISMATCH,
                           f"reads {got}, but {tag} is expected at this location; "
                           f"{got} belongs elsewhere in this cabinet",
                           tag, read, expected)

        d = edit_distance(got, tag.upper())
        if d <= 1:
            return Verdict(ABSTAIN,
                           f"{got} is no tag in this cabinet and differs from the "
                           f"expected {tag} by {d} character; likely a misread. "
                           f"Ask again", tag, read, expected)
        return Verdict(NOT_IN_SCHEMATIC, f"{got} is no tag in this cabinet",
                       tag, read, expected)

    # ----------------------------------------------------------------- strips
    def expected_counts(self, tag: str) -> Counter:
        """Expected terminal count per function for one strip.

        Args:
            tag: Strip tag, e.g. "-X4".

        Returns:
            Counter such as {"N": 8, "L": 8, "PE": 8, "BRACKET": 1}. End
            brackets are included only when COUNT_END_BRACKETS is True.
        """
        total = Counter()
        for r in self.terminals:
            if r["designation"] != tag:
                continue
            if r["type"] == END_BRACKET_TYPE and not COUNT_END_BRACKETS:
                continue
            total += terminal_functions(r["type"])
        return total

    def judge_strip(self, tag: str, counts: dict) -> Verdict:
        """Check spoken terminal counts against the schematic.

        Note: a terminal swapped for another of the same function is invisible
        to this check (CONTEXT §7).

        Args:
            tag: Strip tag, e.g. "-X4".
            counts: Function -> count, e.g. {"N": 8, "L": 8}.

        Returns:
            Verdict: MATCH if every count agrees, MISMATCH listing the
            differences, ABSTAIN if the strip is unknown or no counts given.
        """
        if tag not in STRIP_TAGS:
            return Verdict(ABSTAIN, f"no strip {tag} in the schematic", tag)

        exp = self.expected_counts(tag)
        got = Counter({k.upper(): v for k, v in counts.items() if v is not None})
        expected = {"counts": dict(exp), "tag": tag}
        read = {"counts": dict(got)}

        if not got:
            return Verdict(ABSTAIN, "no counts were given", tag, read, expected)

        diffs = []
        for fn in sorted(set(exp) | set(got)):
            if exp.get(fn, 0) != got.get(fn, 0):
                diffs.append(f"{fn}: read {got.get(fn, 0)}, expected {exp.get(fn, 0)}")

        if not diffs:
            return Verdict(MATCH,
                           "counts per function agree. Note: a terminal swapped "
                           "for another of the same function is invisible to this "
                           "check (CONTEXT §7)", tag, read, expected)
        return Verdict(MISMATCH, "; ".join(diffs), tag, read, expected)


if __name__ == "__main__":
    # Demo cases live in tests/test_adjudicate.py now -- run `pytest` for those.
    adj = Adjudicator.from_export(SCHEMATIC)
    print(f"{len(adj.devices)} devices · {len(adj.terminals)} terminals · "
          f"{len(adj.legal_parts)} legal part numbers\n")

    print("  strips:")
    for tag in STRIP_TAGS:
        print(f"    {tag}  expected {dict(adj.expected_counts(tag))}")