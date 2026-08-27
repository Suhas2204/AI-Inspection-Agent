"""
Block 2 — Position.

Turns schematic coordinates into locations a person can hear and act on:

    Left frame, row 3, position 5   ->   -8F1

Nothing here is verified. The computer cannot tell you whether row 3 is really
the third row you see. Print the sheet, stand at the cabinet, and check it.

Usage:
    python position.py                      # print the walking order
    python position.py --csv walking.csv    # also write a CSV
"""

import argparse
import csv
import json
import sys
from collections import defaultdict

# ---------------------------------------------------------------- settings

DATA = "/data/homes/suhasjagtap/Redlining/data/schematic.cleaned.json"

# Which location prefix is which frame, as the trainee sees it.
# UNVERIFIED — swap these two if the cabinet says otherwise. That check is
# the whole point of Block 2.
FRAMES = {
    "+NSHV+AA00001VLXX": ("left frame", 1),
    "+NSHV+AA00005VLXX": ("right frame", 2),
    "+NSHV+AA00004VRXX": ("left side panel", 3),
    "+NSHV+AA00008VRXX": ("right side panel", 4),
    "": ("no location in file", 9),
}

# Two parts are on the same row if their heights differ by less than this (mm).
# Raise it if the sheet splits one real rail into two. Lower it if it merges
# two real rails into one.
ROW_TOLERANCE_MM = 50.0


# ---------------------------------------------------------------- helpers

def frame_of(record):
    prefix = record["location"].split(".")[0]
    if prefix not in FRAMES:
        print(f"  ! unknown location prefix: {prefix}", file=sys.stderr)
        return prefix, ("unknown frame", 8)
    return prefix, FRAMES[prefix]


def is_terminal(record, shared_tags):
    return record["designation"] in shared_tags


def group_rows(records, tolerance):
    """Cluster records into rows by height. Returns list of rows, top first."""
    # In this export y is negative downward, so the largest y is the top row.
    ordered = sorted(records, key=lambda r: -r["position"]["y"])
    rows, current = [], [ordered[0]]

    for record in ordered[1:]:
        gap = abs(record["position"]["y"] - current[-1]["position"]["y"])
        if gap <= tolerance:
            current.append(record)
        else:
            rows.append(current)
            current = [record]
    rows.append(current)
    return rows


# ---------------------------------------------------------------- main

def build(path, tolerance):
    with open(path) as handle:
        records = json.load(handle)["components"]

    # A tag used by more than one record is a terminal strip label, not a name.
    counts = defaultdict(int)
    for record in records:
        counts[record["designation"]] += 1
    shared_tags = {tag for tag, n in counts.items() if n > 1}

    by_frame = defaultdict(list)
    for record in records:
        prefix, _ = frame_of(record)
        by_frame[prefix].append(record)

    items = []

    for prefix in sorted(by_frame, key=lambda p: FRAMES.get(p, ("", 8))[1]):
        frame_name = FRAMES.get(prefix, ("unknown frame", 8))[0]
        rows = group_rows(by_frame[prefix], tolerance)

        for row_number, row in enumerate(rows, start=1):
            row = sorted(row, key=lambda r: r["position"]["x"])

            # Terminals in this row collapse to one item per strip.
            seen_strips = set()
            position_number = 0

            for record in row:
                tag = record["designation"]

                if is_terminal(record, shared_tags):
                    if tag in seen_strips:
                        continue
                    seen_strips.add(tag)
                    members = [r for r in row if r["designation"] == tag]
                    position_number += 1
                    items.append({
                        "frame": frame_name,
                        "row": row_number,
                        "position": position_number,
                        "tag": tag,
                        "kind": "strip",
                        "detail": f"{len(members)} terminals",
                        "spoken": f"{frame_name}, row {row_number}, "
                                  f"strip {tag.lstrip('-')}",
                    })
                else:
                    position_number += 1
                    items.append({
                        "frame": frame_name,
                        "row": row_number,
                        "position": position_number,
                        "tag": tag,
                        "kind": "device",
                        "detail": record["type"],
                        "spoken": f"{frame_name}, row {row_number}, "
                                  f"position {position_number}",
                    })

    return items


def show(items):
    current = None
    for item in items:
        header = (item["frame"], item["row"])
        if header != current:
            current = header
            print()
            print(f"  {item['frame'].upper()} — ROW {item['row']}")
            print("  " + "-" * 74)
        print(f"  [ ]  pos {item['position']:>2}   {item['tag']:<8} "
              f"{item['detail'][:44]}")

    devices = sum(1 for i in items if i["kind"] == "device")
    strips = sum(1 for i in items if i["kind"] == "strip")
    print()
    print("  " + "=" * 74)
    print(f"  {devices} devices + {strips} strips = {len(items)} items")
    if len(items) != 100:
        print("  ! expected 100 — check ROW_TOLERANCE_MM and the frame map")
    print()
    print("  Now print this and check it against the cabinet, item by item.")
    print("  Tick the box only when you have seen the part with your own eyes.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=DATA)
    parser.add_argument("--tolerance", type=float, default=ROW_TOLERANCE_MM)
    parser.add_argument("--csv")
    args = parser.parse_args()

    items = build(args.data, args.tolerance)
    show(items)

    if args.csv:
        with open(args.csv, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(items[0]))
            writer.writeheader()
            writer.writerows(items)
        print(f"  wrote {args.csv}")


if __name__ == "__main__":
    main()
