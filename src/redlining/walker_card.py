"""Block 9: print the card the walker reads while planting the fault set.

    uv run python -m redlining.walker_card

Every checklist item, in the order session.py prompts -- band first, then
walking order within the band -- with what to speak at each one. Positions
carrying a planted fault are overwritten from faults.csv.

Nothing on the card says which lines were overwritten. A card that marks
its own faults measures nothing: the walker would read the marks, not the
cabinet. The fault set lives in faults.csv and nowhere else.

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


def card(items, override: dict[str, str]) -> list[str]:
    """Render the card, one line per checklist item.

    Args:
        items: Checklist items, already in the order session.py prompts.
        override: Faulted position -> what to speak there.

    Returns:
        The lines to print.
    """
    unplaceable = sorted(set(override) - {i.tag for i in items})
    if unplaceable:
        sys.exit(f"fault position(s) not on the checklist: {', '.join(unplaceable)}")

    L = [f"WALKER CARD   cabinet 20160387   {len(items)} positions",
         "In the order the app asks. Read the position, speak what the card says.",
         "",
         f"{'#':>3}  {'band':<6}{'position':<46}{'speak'}",
         f"{'':>3}  {'-' * 6}{'-' * 46}{'-' * 30}"]
    band = None
    for n, item in enumerate(items, 1):
        if item.band != band:
            band = item.band
            L.append("")
        where = item.spoken
        if item.kind == "strip":
            where += f"  ({item.detail})"
        L.append(f"{n:>3}  {item.band:<6}{where:<46}"
                 f"{override.get(item.tag, item.tag)}")
    return L


def main() -> None:
    """CLI: print the walker card for the current fault set."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--faults", type=Path, default=FAULTS)
    args = ap.parse_args()

    items = load_checklist()
    override = load_overrides(args.faults)
    print("\n".join(card(items, override)))


if __name__ == "__main__":
    main()
