"""
Block 2 — Position.

Turns schematic coordinates into locations a person can hear and act on:

    left frame, row 4, position 5   ->   -7F1

HOW ROWS ARE FOUND (changed 31 Aug, after the first live run)

The old version clustered records by height with ROW_TOLERANCE_MM and produced
ten rows per frame where the cabinet has five. It was guessing at something the
export already states.

The DIN rails are records in their own right: type ED2, tagged -D1..-D5 in the
left frame and -D11..-D15 in the right, all 495 mm wide. Every device sits at
exactly its rail's y. So a row is not a cluster -- it is a rail, named by the
rail's own record, and a device belongs to the rail whose y it matches.

The ED138 and ED12 records are wire ducts, sitting BETWEEN rails at -287.5,
-512.5, -587.5, -1112.5 and -1900. Those heights were the phantom rows.

Nothing here is verified. The computer cannot tell you whether row 3 is really
the third row you see. Print the sheet, stand at the cabinet, check it.

Usage:
    python position.py
    python position.py --csv data/walking_order.csv
    python position.py --include-structural      # keep rails and ducts as items
"""

import argparse
import csv
import json
import sys
from collections import defaultdict

DATA = "data/schematic.cleaned.json"

# Which location prefix is which frame, as the trainee sees it.
# UNVERIFIED -- swap the first two if the cabinet says otherwise.
FRAMES = {
    "+NSHV+AA00001VLXX": ("left frame", 1),
    "+NSHV+AA00005VLXX": ("right frame", 2),
    "+NSHV+AA00004VRXX": ("left side panel", 3),
    "+NSHV+AA00008VRXX": ("right side panel", 4),
    "": ("no location in file", 9),
}

# Structural parts: the metalwork components clip onto, not components.
RAIL_TYPE = "ED2"                      # DIN rail, 495 mm, tagged -D*
DUCT_TYPES = {"ED138", "ED12"}         # wire duct, tagged -J*
STRUCTURAL = {RAIL_TYPE} | DUCT_TYPES

# A device belongs to a rail if their heights differ by less than this. Devices
# sit at exactly the rail's y in this export, so this is a sanity margin, not a
# clustering knob. If anything lands outside it, that is reported, not absorbed.
RAIL_SNAP_MM = 1.0


def frame_of(record):
    prefix = record["location"].split(".")[0]
    if prefix not in FRAMES:
        print(f"  ! unknown location prefix: {prefix}", file=sys.stderr)
        return prefix, ("unknown frame", 8)
    return prefix, FRAMES[prefix]


def build(path, include_structural=False):
    with open(path) as handle:
        records = json.load(handle)["components"]

    counts = defaultdict(int)
    for record in records:
        counts[record["designation"]] += 1
    shared_tags = {tag for tag, n in counts.items() if n > 1}

    by_frame = defaultdict(list)
    for record in records:
        prefix, _ = frame_of(record)
        by_frame[prefix].append(record)

    items, orphans = [], []

    for prefix in sorted(by_frame, key=lambda p: FRAMES.get(p, ("", 8))[1]):
        frame_name = FRAMES.get(prefix, ("unknown frame", 8))[0]
        in_frame = by_frame[prefix]

        # The rails, top first. y is negative downward, so largest y is highest.
        rails = sorted((r for r in in_frame if r["type"] == RAIL_TYPE),
                       key=lambda r: -r["position"]["y"])

        mounted = [r for r in in_frame
                   if include_structural or r["type"] not in STRUCTURAL]

        if not rails:
            # No rail records here (side panels, unlocated). Keep the parts in a
            # single row rather than inventing a structure the file does not have.
            if mounted:
                items.extend(_emit_row(frame_name, 1, mounted, shared_tags))
            continue

        assigned = set()
        for row_number, rail in enumerate(rails, start=1):
            rail_y = rail["position"]["y"]
            on_rail = [r for r in mounted
                       if abs(r["position"]["y"] - rail_y) <= RAIL_SNAP_MM]
            assigned.update(id(r) for r in on_rail)
            if on_rail:
                items.extend(_emit_row(frame_name, row_number, on_rail,
                                       shared_tags, rail["designation"]))

        for r in mounted:
            if id(r) not in assigned:
                orphans.append((frame_name, r))

    return items, orphans


def _emit_row(frame_name, row_number, row, shared_tags, rail_tag=None):
    """One rail's worth of items, ordered left to right."""
    out = []
    row = sorted(row, key=lambda r: r["position"]["x"])
    seen_strips = set()
    position_number = 0

    for record in row:
        tag = record["designation"]
        if tag in shared_tags:                       # terminal strip
            if tag in seen_strips:
                continue
            seen_strips.add(tag)
            members = [r for r in row if r["designation"] == tag]
            position_number += 1
            out.append({
                "frame": frame_name, "row": row_number,
                "position": position_number, "tag": tag, "kind": "strip",
                "detail": f"{len(members)} terminals",
                "rail": rail_tag or "",
                "spoken": f"{frame_name}, row {row_number}, "
                          f"strip {tag.lstrip('-')}",
            })
        else:
            position_number += 1
            out.append({
                "frame": frame_name, "row": row_number,
                "position": position_number, "tag": tag, "kind": "device",
                "detail": record["type"], "rail": rail_tag or "",
                "spoken": f"{frame_name}, row {row_number}, "
                          f"position {position_number}",
            })
    return out


def show(items, orphans, include_structural):
    current = None
    for item in items:
        header = (item["frame"], item["row"])
        if header != current:
            current = header
            rail = f"   (rail {item['rail']})" if item["rail"] else ""
            print(f"\n  {item['frame'].upper()} — ROW {item['row']}{rail}")
            print("  " + "-" * 74)
        print(f"  [ ]  pos {item['position']:>2}   {item['tag']:<8} "
              f"{item['detail'][:44]}")

    devices = sum(1 for i in items if i["kind"] == "device")
    strips = sum(1 for i in items if i["kind"] == "strip")
    rows = len({(i["frame"], i["row"]) for i in items})

    print("\n  " + "=" * 74)
    print(f"  {devices} devices + {strips} strips = {len(items)} items, "
          f"across {rows} rows")
    print(f"  structural parts (rails, ducts): "
          f"{'INCLUDED as items' if include_structural else 'excluded'}")
    if not include_structural:
        print("  -- run with --include-structural to see the other number.")
        print("  -- CONTEXT §6 says 70 items and assumes they are included.")

    if orphans:
        print(f"\n  ! {len(orphans)} part(s) sit at no rail height. Not guessed at:")
        for frame_name, r in orphans:
            print(f"      {r['designation']:8} {frame_name}, "
                  f"y={r['position']['y']:.1f}  {r['type']}")

    print("\n  Now print this and check it against the cabinet, item by item.")
    print("  Tick a box only when you have seen the part with your own eyes.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=DATA)
    parser.add_argument("--csv")
    parser.add_argument("--include-structural", action="store_true",
                        help="keep DIN rails and wire ducts as checklist items")
    args = parser.parse_args()

    items, orphans = build(args.data, args.include_structural)
    show(items, orphans, args.include_structural)

    if args.csv:
        with open(args.csv, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(items[0]))
            writer.writeheader()
            writer.writerows(items)
        print(f"\n  wrote {args.csv}")


if __name__ == "__main__":
    main()