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

- UNVERIFIED: whether position is a part's corner or its centre. The export
  does not say, and it is not inferable from one file. The box anchor is
  passed through as exported; a viewer that assumes the wrong one will be
  offset by half a part. Settle this against the CAD model before trusting
  any overlap or collision read off these boxes.

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
