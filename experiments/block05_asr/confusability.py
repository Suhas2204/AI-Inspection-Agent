"""Block 9, Track 2 -- the confusability map.

What this answers, before a single run is scored:

    Which device tags are close enough that one misheard character turns a
    correct read into a DIFFERENT TAG THAT ALSO EXISTS in this cabinet?

That is the dangerous class. A misread that produces nonsense is caught -- the
adjudicator returns not-in-schematic and the trainee is asked again. A misread
that produces another legal tag is NOT caught: it comes back as a confident
mismatch, or, if the neighbour happens to be the item under inspection, as a
confident match. Either way it looks like a verdict rather than an error, and
nothing downstream can tell the difference.

So this is the ceiling on voice-only inspection FOR THIS CABINET. It is a
property of the schematic, not of Whisper, and it needs no audio, no run and no
model to compute. It is also the evidence-based version of the Phase 2 camera
argument: the camera is not wanted because cameras are nice, it is wanted
because N pairs here are provably indistinguishable by ear.

Two distances are reported:

  * edit distance 1 -- one character inserted, deleted or substituted.
  * phonetic        -- characters that are confusable when SPOKEN, which edit
                       distance alone does not model. "F" and "S", "B" and "D",
                       "13" and "30". A pair at edit distance 1 whose differing
                       characters are also phonetically close is worse than one
                       that differs in an unambiguous digit.

Adjacency matters too. A twin on the far side of the cabinet is a mismatch the
trainee will notice. A twin at the next position on the same rail is one the
system will silently accept, because the trainee's eye and the recogniser can
slip together. Adjacent pairs are therefore counted separately.

Usage:
    python experiments/block09_eval/confusability.py
    python experiments/block09_eval/confusability.py --csv data/confusability.csv

Nothing here is verified against speech. It says what COULD collide, not what
does. Track 1 (ASR character accuracy) is what tells you whether these
collisions actually happen.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path

DATA = "data/schematic.cleaned.json"
ORDER = "data/walking_order.csv"

# Structural: the metalwork components clip onto. Excluded from the checklist
# per CONTEXT §10, so excluded here -- they are never spoken.
STRUCTURAL = {"ED2", "ED138", "ED12"}

# Characters that collide when spoken aloud, especially in accented English.
# Grouped: any two members of a group are treated as phonetically confusable.
# This is engineering judgement, not a measured confusion matrix. Track 1
# replaces it with real numbers; until then it is flagged as an ASSUMPTION.
PHONETIC_GROUPS = [
    set("FS"),        # "eff" / "ess"
    set("BDEGPTVZ3"), # the E-set: bee, dee, gee, pee, tee, vee, zee, three
    set("MN"),        # em / en
    set("AK8"),       # ay / kay / eight
    set("IY5"),       # eye / why / five
    set("QU2"),       # cue / you / two
    set("CZ"),
    set("14"),        # "one" / "four" clipped
    set("69"),        # "six" / "nine" over a poor microphone
    set("07O"),       # oh / seven / letter O
]


def phonetically_close(a: str, b: str) -> bool:
    """True if a and b are single characters that collide when spoken."""
    if a == b:
        return True
    return any(a in group and b in group for group in PHONETIC_GROUPS)


def edit_distance(a: str, b: str) -> int:
    """Plain Levenshtein. Short strings, so the naive version is fine."""
    if abs(len(a) - len(b)) > 2:
        return 99
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            current[j] = min(previous[j] + 1,
                             current[j - 1] + 1,
                             previous[j - 1] + (ca != cb))
        previous = current
    return previous[len(b)]


def differing_chars(a: str, b: str):
    """The single substituted pair, if the difference IS a substitution.

    Returns None for insertions and deletions, where there is no pair to
    compare phonetically.
    """
    if len(a) != len(b):
        return None
    diff = [(x, y) for x, y in zip(a, b) if x != y]
    return diff[0] if len(diff) == 1 else None


def load_device_tags(path: str) -> list[str]:
    """The 62 spoken device tags. Terminals share a strip tag and are read as
    counts, not tags, so they are excluded -- there is no tag to mishear."""
    records = json.load(open(path))["components"]
    counts = Counter(r["designation"] for r in records)
    return sorted({r["designation"] for r in records
                   if counts[r["designation"]] == 1
                   and r["type"] not in STRUCTURAL})


def load_adjacency(path: str) -> dict[str, set[str]]:
    """Which tags sit next to each other in the order the trainee walks.

    Neighbours on the same rail are what matter: that is where a slip of the
    eye and a slip of the recogniser can agree with each other.
    """
    neighbours: dict[str, set[str]] = defaultdict(set)
    try:
        rows = list(csv.DictReader(open(path)))
    except FileNotFoundError:
        return neighbours
    by_row = defaultdict(list)
    for r in rows:
        if r.get("kind") == "device":
            by_row[(r["frame"], r["row"])].append(r["tag"])
    for tags in by_row.values():
        for a, b in zip(tags, tags[1:]):
            neighbours[a].add(b)
            neighbours[b].add(a)
    return neighbours


def build(data_path: str, order_path: str):
    tags = load_device_tags(data_path)
    neighbours = load_adjacency(order_path)
    pairs = []

    for a, b in itertools.combinations(tags, 2):
        distance = edit_distance(a, b)
        if distance > 1:
            continue
        substitution = differing_chars(a, b)
        phonetic = bool(substitution and phonetically_close(*substitution))
        pairs.append({
            "tag_a": a,
            "tag_b": b,
            "edit_distance": distance,
            "differs": f"{substitution[0]}/{substitution[1]}" if substitution else "len",
            "phonetic": phonetic,
            "adjacent": b in neighbours.get(a, ()),
        })
    return tags, pairs


def report(tags, pairs) -> None:
    at_risk = {t for p in pairs for t in (p["tag_a"], p["tag_b"])}
    phonetic = [p for p in pairs if p["phonetic"]]
    adjacent = [p for p in pairs if p["adjacent"]]
    both = [p for p in pairs if p["phonetic"] and p["adjacent"]]

    print(f"\n  {len(tags)} spoken device tags")
    print(f"  {len(pairs)} pairs at edit distance 1")
    print(f"  {len(at_risk)} tags ({100 * len(at_risk) / len(tags):.0f}%) have "
          f"at least one one-character twin")
    print(f"  {len(phonetic)} of those pairs also differ phonetically")
    print(f"  {len(adjacent)} sit next to each other on the same rail")
    print(f"  {len(both)} are BOTH -- the worst case\n")

    if both:
        print("  Worst case, phonetically close AND physically adjacent:")
        for p in both:
            print(f"      {p['tag_a']:<8} vs {p['tag_b']:<8}  ({p['differs']})")
        print()

    print("  A misread inside any of these pairs produces a tag that EXISTS.")
    print("  The adjudicator cannot distinguish it from a real finding, so it")
    print("  is reported as a verdict rather than caught as an error.")
    print("  This is the ceiling on voice-only inspection for this cabinet.\n")
    print("  ASSUMPTION: the phonetic groups are judgement, not measurement.")
    print("  Block 9 Track 1 replaces them with a real confusion matrix.\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=DATA)
    parser.add_argument("--order", default=ORDER)
    parser.add_argument("--csv", help="write the full pair list")
    args = parser.parse_args()

    tags, pairs = build(args.data, args.order)
    report(tags, pairs)

    if args.csv:
        Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        with open(args.csv, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(pairs[0]))
            writer.writeheader()
            writer.writerows(pairs)
        print(f"  wrote {args.csv}\n")


if __name__ == "__main__":
    main()
