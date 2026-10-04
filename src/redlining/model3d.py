"""Axis-aligned boxes for the 3D view: one box per cleaned component, in mm.

Built from loader.py's output, never from the raw export. The raw file still
holds the 42 mechanical filler parts, the 5 '- Kombination' wrappers, and the
unmerged -1Q2/-1Q3 records whose position is all zeros; the cleaned file has
the filler gone and those two coordinates merged in from their wrapper twins.
Reading the raw export here would put phantom boxes at the origin.

Units are millimetres for all six numbers. The export declares no unit
anywhere -- mm is read off the parts whose type name carries their own size
('Wire ridge 200mm' has width 200.0) and off the ED2 DIN rail at width 495.0,
which position.py already documents as 495 mm.

y is negative downward, as in position.py: the largest y is the highest part.
Boxes are returned in the export's own frame, not re-centred or flipped.

The anchor is a corner, not a centre: position is the low edge on all three
axes, so a box runs [x, x+w], [y, y+h], [z, z+d]. Because y grows upward, the
low edge in y is the part's bottom. Measured off this export three ways:

- Rail containment. All 143 parts mounted on an ED2 rail fall inside that
  rail's 495 mm x-span. Read as centres only 103 of 143 do, and -14K1 ends up
  154.5 mm past the end of the rail it is clipped to.
- Overlap. No two of the 173 boxes interpenetrate. Read as centres, 43 pairs
  do, 9 of them between non-structural parts -- 43 impossibilities.
- The 900 mm ducts. The four ED12 ducts sit at y=-1900. As a bottom edge they
  reach y=-1000 and fill the cabinet; as a top edge they would reach y=-2800,
  900 mm below every other part in the file.

x and z are pinned hard by the first two counts. y is the weaker leg: parts on
one rail share an identical y, so overlap cannot separate them at all, and the
duct argument assumes those ducts stand on the cabinet floor. Confirm y
against the CAD model before trusting a vertical clearance read off these
boxes. The anchor is still passed through as exported -- this note records
which convention that pass-through turned out to be, and changes no number.

Run:
    uv run python -m redlining.model3d
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .paths import SCHEMATIC
from .position import frame_of      # one definition of "which frame a part is in"

DATA = SCHEMATIC

# A part exported with a zero height or depth would be an invisible box. Give it
# a token edge instead of dropping it, so it stays countable and clickable.
# This is a floor for display, not a measurement: a clamped edge is not the
# part's real size, and nothing downstream should treat it as one.
MIN_SIZE_MM = 5.0


def clamp_size(value: float) -> float:
    """Raise a zero or missing edge length to the display floor.

    Args:
        value: Edge length in mm from the export, possibly 0.0.

    Returns:
        The value, or MIN_SIZE_MM if it is not a positive number.
    """
    if not isinstance(value, (int, float)) or value <= 0:
        return MIN_SIZE_MM
    return float(value)


def build_boxes(path: Path = DATA) -> list[dict]:
    """Turn every cleaned component into one axis-aligned box.

    One box per record, not per tag: the 8 terminal strips are many records
    sharing a designation, so -X5 comes back as 20 boxes. Collapsing them into
    one block is a view's decision, made from these boxes, not here.

    Args:
        path: Cleaned schematic JSON, i.e. loader.py's output.

    Returns:
        Box dicts with tag, frame, x, y, z, w, h, d -- all lengths in mm,
        every edge at least MIN_SIZE_MM. Order follows the cleaned file.
    """
    with open(path, encoding="utf-8") as handle:
        records = json.load(handle)["components"]

    boxes = []
    for record in records:
        position = record["position"]
        dimensions = record["dimensions"]
        boxes.append({
            "tag": record["designation"],
            "frame": frame_of(record)[1][0],
            "x": float(position["x"]),
            "y": float(position["y"]),
            "z": float(position["z"]),
            "w": clamp_size(dimensions["width"]),
            "h": clamp_size(dimensions["height"]),
            "d": clamp_size(dimensions["depth"]),
        })
    return boxes


# How the viewer paints a box. Here rather than in the page so it can be
# tested without starting Streamlit, and so app.py stays the thin front end
# its own docstring says it is. Nothing here imports adjudicate: an outcome
# arrives as the plain string the run logged, so this module has no opinion
# about how that verdict was reached.
FRAME_COLOURS = {
    "left frame": "#4e79a7",
    "right frame": "#f28e2b",
    "left side panel": "#9c755f",     # brown: green belongs to the current item
    "right side panel": "#b07aa1",
}
UNKNOWN_FRAME_COLOUR = "#9c9c9c"

# A part the run has not answered yet: one uniform cube on the part's own
# centre, no tag, no size. Both are what a trainee would otherwise read off
# the screen instead of off the cabinet.
PLACEHOLDER_MM = 5.0
PLACEHOLDER_COLOUR = "#9aa0a6"
PLACEHOLDER_HOVER = "not read yet"

# The item the run is on: big enough to find at a glance, and still unnamed,
# because the view says where to go, not what will be found there.
CURRENT_MM = 30.0
CURRENT_COLOUR = "#2e8b3d"
CURRENT_HOVER = "next to read"


def centred_cube(box: dict, mm: float) -> dict:
    """The same box reduced to a cube of edge mm on its own centre.

    Args:
        box: A box dict from build_boxes().
        mm: Edge length of the cube.

    Returns:
        A box dict with the cube's corner and size; every other key is kept,
        so the real size stays reachable through the original box.
    """
    half = mm / 2.0
    return {**box,
            "x": box["x"] + box["w"] / 2.0 - half,
            "y": box["y"] + box["h"] / 2.0 - half,
            "z": box["z"] + box["d"] / 2.0 - half,
            "w": mm, "h": mm, "d": mm}


def box_style(box: dict, outcome: str | None = None,
              structural: bool = False,
              current: bool = False) -> tuple[dict, str, str]:
    """How one box is drawn: its geometry, its colour, and its hover.

    Precedence is current, then answered or structural, then unanswered. The
    current item wins over its own answer so that a re-ask still points at
    one place.

    Args:
        box: A box dict from build_boxes().
        outcome: The run's verdict for this tag, e.g. "match" or "abstain",
            or None if the run has not answered it.
        structural: True for rails and ducts, which are drawn true all run.
        current: True for the one box the run is sending the trainee to.

    Returns:
        (drawn_box, colour, hover). drawn_box is the real box when it is
        answered, structural or nothing special, and a cube on its centre
        when it is the current item or still unanswered.
    """
    if current:
        return centred_cube(box, CURRENT_MM), CURRENT_COLOUR, CURRENT_HOVER

    if outcome is None and not structural:
        return (centred_cube(box, PLACEHOLDER_MM), PLACEHOLDER_COLOUR,
                PLACEHOLDER_HOVER)

    colour = FRAME_COLOURS.get(box["frame"], UNKNOWN_FRAME_COLOUR)
    hover = (f"{box['tag']} — {box['frame']}<br>"
             f"{box['w']:.1f} × {box['h']:.1f} × {box['d']:.1f} mm")
    if outcome is not None:
        hover += f"<br>{outcome}"
    return box, colour, hover


def representative_index(boxes: list[dict], tag: str) -> int | None:
    """Index of the single box that stands for a tag.

    A device is one box, but a terminal strip is many -- -X5 is 20 of them --
    and a view marking "the item the trainee is being sent to" has to mark one
    thing, not twenty. The representative is the one the walk reaches first:
    topmost, then leftmost, then furthest back. y is negative downward, so
    topmost is the largest y; the order matches position.py's top-to-bottom,
    left-to-right walk.

    Args:
        boxes: Boxes from build_boxes().
        tag: A checklist item's tag, e.g. "-8F7" or "-X5".

    Returns:
        The index into boxes, or None if no box carries that tag. Never a
        list: the caller marks exactly one box or none.
    """
    found = [n for n, box in enumerate(boxes) if box["tag"] == tag]
    if not found:
        return None
    return min(found, key=lambda n: (-boxes[n]["y"], boxes[n]["x"],
                                     boxes[n]["z"]))


def main() -> None:
    """CLI: build the boxes and print what came out, per frame."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DATA)
    args = parser.parse_args()

    boxes = build_boxes(args.data)
    clamped = [b for b in boxes
               if MIN_SIZE_MM in (b["w"], b["h"], b["d"])]

    print(f"{len(boxes)} boxes from {args.data}")
    for frame in dict.fromkeys(b["frame"] for b in boxes):
        n = sum(1 for b in boxes if b["frame"] == frame)
        print(f"  {n:4d}  {frame}")

    for axis in ("x", "y", "z"):
        lo = min(b[axis] for b in boxes)
        hi = max(b[axis] for b in boxes)
        print(f"  {axis}: {lo:9.1f} .. {hi:9.1f} mm")

    print(f"\n  {len(clamped)} box(es) have an edge at the {MIN_SIZE_MM:.0f} mm "
          f"floor -- their real size is not in the file.")
    for b in clamped:
        print(f"      {b['tag']:8} w={b['w']:.1f} h={b['h']:.1f} d={b['d']:.1f}")


if __name__ == "__main__":
    main()
