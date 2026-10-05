"""Block 9: print the card the walker reads while planting the fault set.

    uv run python -m redlining.walker_card

Every checklist item, in the order session.py prompts -- band first, then
walking order within the band -- with what to speak at each one. Positions
carrying a planted fault are overwritten from faults.csv.

Nothing on the card says which lines were overwritten. A card that marks
its own faults measures nothing: the walker would read the marks, not the
cabinet. The fault set lives in faults.csv and nowhere else.

Two versions, because v1 broke that rule at the strips. v1 prints a strip's
TAG in the speak column when the strip is unfaulted and a sentence when it
is faulted, so 6 of 8 strips read "-X1", "-X2", ... and exactly the 2
faulted ones read an instruction. The tell is visible at a glance, without
reading a word of it, and it names the fault set. v1 also tells the walker
to speak "-X1" at a strip, which is not what the app asks for there: at a
strip it asks for terminal counts.

v2 gives every strip an instruction of the same shape -- each one begins
"count the terminals" -- so there is no form to read off, and the unfaulted
strips finally say what the walker is actually meant to do.

What v2 does NOT fix, and cannot: a faulted strip's instruction still says
something unusual, because that instruction IS the planted fault. A walker
who reads and thinks about "count as if one L terminal were absent" knows
that strip is special. Only the glanceable tell is gone. Devices never had
this problem -- a faulted device shows another tag, indistinguishable in
form from a correct one.

v1 is kept and still reproducible: run 20260927-130613 was walked with it,
and experiments/block05_asr/score.py checks its reference against the card
that was actually read. Printing v2 over walker_card.txt would silently
invalidate that check.

The overwrites are read from each fault's what_i_do, which the candidates
file writes as one "card says: at <position> ..." clause per position:

    card says: at -12F5 position speak -12F6; at -12F6 position speak -12F5
    card says: at -X3 count as if one L terminal were absent

A clause that does not parse stops the card rather than printing a line
that silently says the wrong thing.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

from .checklist import load_checklist
from .paths import DECISIONS

FAULTS = DECISIONS / "faults.csv"
PREFIX = "card says: "
CLAUSE = re.compile(r"^at (\S+) (?:position speak (\S+)|(.+))$")

VERSIONS = (1, 2)
CURRENT_VERSION = 2           # what a NEW run should be walked with

# v2's strip wording. Every strip line starts with STRIP_STEM, faulted or
# not, which is what removes the glanceable tell; see the module docstring
# for the part of it that cannot be removed.
STRIP_STEM = "count the terminals"
STRIP_NORMAL = f"{STRIP_STEM}, left to right"


def load_overrides(path: Path = FAULTS) -> dict[str, str]:
    """Map each faulted position to the line the card should show there.

    Args:
        path: faults.csv, as written by select_faults.

    Returns:
        {position: text to speak}. A label swap contributes two entries.

    Raises:
        SystemExit: A what_i_do is not a card instruction, a clause does not
            parse, or two faults claim one position.
    """
    with path.open(encoding="utf-8") as fh:
        faults = list(csv.DictReader(fh))
    if not faults:
        sys.exit(f"{path} is empty; there is no fault set to plant.")

    override: dict[str, str] = {}
    for f in faults:
        text = f["what_i_do"]
        if not text.startswith(PREFIX):
            sys.exit(f"{f['id']}: what_i_do is not a card instruction: {text!r}")
        for clause in text[len(PREFIX):].split(";"):
            m = CLAUSE.match(clause.strip())
            if not m:
                sys.exit(f"{f['id']}: cannot parse clause {clause.strip()!r}")
            position, speak, instruction = m.groups()
            if position in override:
                sys.exit(f"two faults write position {position}")
            override[position] = speak or instruction

    expected = sum(2 if f["item_b"] else 1 for f in faults)
    if len(override) != expected:
        sys.exit(f"{len(override)} clause(s) for {expected} fault position(s)")
    return override


def strip_line_v2(tag: str, override: dict[str, str]) -> str:
    """What v2 prints in a strip's instruction column.

    Every return value starts with STRIP_STEM, faulted or not. That is the
    whole mechanism: see the module docstring for what it fixes and what it
    does not.

    Args:
        tag: Strip tag, e.g. "-X3".
        override: Faulted position -> what the card should show there.

    Returns:
        The instruction, e.g. "count the terminals, omit the bracket count".

    Raises:
        SystemExit: If this strip's fault is written as a tag to speak. v2
            has no uniform way to render that at a strip, and inventing one
            would print a line that quietly says the wrong thing.
    """
    instruction = override.get(tag)
    if instruction is None:
        return STRIP_NORMAL
    if " " not in instruction:
        sys.exit(
            f"{tag}: the fault for this strip says to speak {instruction!r}, "
            f"but a strip is spoken as counts, so v2 cannot render it as a "
            f"counting instruction. Write the fault as an instruction in "
            f"faults.csv, or print this card with --version 1."
        )
    if instruction.startswith(STRIP_STEM):
        return instruction
    if instruction.startswith("count "):
        # Already an instruction in the right register, e.g. "count as if one
        # L terminal were absent". Reworded so that every strip line opens
        # the same way, with the fault's own words kept after the stem.
        return f"{STRIP_STEM}, {instruction[len('count '):]}"
    return f"{STRIP_STEM}, {instruction}"


def card(items, override: dict[str, str], version: int = 1) -> list[str]:
    """Render the card, one line per checklist item.

    Args:
        items: Checklist items, already in the order session.py prompts.
        override: Faulted position -> what to speak there.
        version: 1 reproduces the card run 20260927-130613 was walked with,
            line for line. 2 is CURRENT_VERSION and the one to walk next; the
            two differ only at the strips. Defaults to 1 so that every
            existing caller keeps checking against the card that was read.

    Returns:
        The lines to print.

    Raises:
        SystemExit: On an unknown version, a fault position that is not on
            the checklist, or (v2 only) a strip fault it cannot render.
    """
    if version not in VERSIONS:
        sys.exit(f"no card version {version}; known: "
                 f"{', '.join(str(v) for v in VERSIONS)}")

    unplaceable = sorted(set(override) - {i.tag for i in items})
    if unplaceable:
        sys.exit(f"fault position(s) not on the checklist: {', '.join(unplaceable)}")

    if version == 1:
        title = f"WALKER CARD   cabinet 20160387   {len(items)} positions"
        header = ("In the order the app asks. Read the position, speak what "
                  "the card says.")
        column = "speak"
    else:
        title = (f"WALKER CARD   cabinet 20160387   {len(items)} positions"
                 f"   v{version}")
        header = ("In the order the app asks. Read the position, then do what "
                  "the card says.")
        column = "say / do"

    L = [title,
         header,
         "",
         f"{'#':>3}  {'band':<6}{'position':<46}{column}",
         f"{'':>3}  {'-' * 6}{'-' * 46}{'-' * 30}"]
    band = None
    for n, item in enumerate(items, 1):
        if item.band != band:
            band = item.band
            L.append("")
        where = item.spoken
        if item.kind == "strip":
            where += f"  ({item.detail})"
        if version == 1 or item.kind != "strip":
            says = override.get(item.tag, item.tag)
        else:
            says = strip_line_v2(item.tag, override)
        L.append(f"{n:>3}  {item.band:<6}{where:<46}{says}")
    return L


def main() -> None:
    """CLI: print the walker card for the current fault set."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--faults", type=Path, default=FAULTS)
    ap.add_argument("--version", type=int, default=CURRENT_VERSION,
                    choices=VERSIONS,
                    help=f"card version to print (default {CURRENT_VERSION}; "
                         f"1 reproduces the card run 20260927-130613 was "
                         f"walked with)")
    args = ap.parse_args()

    items = load_checklist()
    override = load_overrides(args.faults)
    print("\n".join(card(items, override, version=args.version)))


if __name__ == "__main__":
    main()
