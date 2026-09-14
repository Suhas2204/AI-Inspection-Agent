"""Block 9, Track 2: the confusability map for spoken device tags.

- Question: which tags are one misheard character away from ANOTHER REAL tag?
  That misread is not caught -- it returns a confident mismatch (or match)
  instead of not-in-schematic. It is the ceiling on voice-only inspection here.
- A property of the schematic, not of Whisper: no audio, run or model needed.
- Reports pairs at edit distance 1, and marks pairs whose differing characters
  sound alike ("phonetic") or sit next to each other on a rail ("adjacent").
- Says what COULD collide, not what does. Track 1 (ASR accuracy) measures that.

Run:
    uv run python experiments/block05_asr/confusability.py
    uv run python experiments/block05_asr/confusability.py --csv data/confusability.csv
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
    """Check whether two single characters sound alike when spoken.

    Args:
        a: One character.
        b: Another character.

    Returns:
        True if they are equal or in the same PHONETIC_GROUPS set.
    """
    if a == b:
        return True
    return any(a in group and b in group for group in PHONETIC_GROUPS)


def edit_distance(a: str, b: str) -> int:
    """Plain Levenshtein distance (the naive version is fine for short tags).

    Args:
        a: First string.
        b: Second string.

    Returns:
        Edit distance, or 99 if the lengths differ by more than 2.
    """
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
    """Return the one substituted character pair between two strings.

    Args:
        a: First string.
        b: Second string.

    Returns:
        (char_a, char_b) if exactly one position differs, else None. Also None
        for insertions/deletions, which have no pair to compare phonetically.
    """
    if len(a) != len(b):
        return None
    diff = [(x, y) for x, y in zip(a, b) if x != y]
    return diff[0] if len(diff) == 1 else None


def load_device_tags(path: str) -> list[str]:
    """Load the spoken device tags (62 in this cabinet).

    Strip terminals share a tag and are read as counts, so they are excluded,
    as are structural parts.

    Args:
        path: Cleaned schematic JSON.

    Returns:
        Sorted list of unique device tags.
    """
    records = json.load(open(path))["components"]
    counts = Counter(r["designation"] for r in records)
    return sorted({r["designation"] for r in records
                   if counts[r["designation"]] == 1
                   and r["type"] not in STRUCTURAL})


def load_adjacency(path: str) -> dict[str, set[str]]:
    """Find which device tags are neighbours on the same rail in walking order.

    Same-rail neighbours matter most: a slip of the eye and a slip of the
    recogniser can agree there.

    Args:
        path: walking_order.csv.

    Returns:
        Dict tag -> set of neighbouring tags. Empty if the file is missing.
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
    """Find every pair of device tags at edit distance 1.

    Args:
        data_path: Cleaned schematic JSON.
        order_path: walking_order.csv, for adjacency.

    Returns:
        (tags, pairs): all tags, and one dict per pair with tag_a, tag_b,
        edit_distance, differs, phonetic, adjacent.
    """
    tags =load_device_tags(data_path)
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
    """Print the headline numbers and the worst-case pairs.

    Args:
        tags: All spoken device tags.
        pairs: Pair dicts from build().
    """
    at_risk ={t for p in pairs for t in (p["tag_a"], p["tag_b"])}
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
    """CLI: build the confusability map, print it, and optionally write a CSV."""
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
