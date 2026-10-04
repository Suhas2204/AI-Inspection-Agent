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
from .position import STRUCTURAL
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


# The 12 triangles of a cuboid, indexing the 8 corners box_corners() emits.
CUBOID_FACES = [
    (0, 1, 2), (0, 2, 3),        # z = z        (back)
    (4, 5, 6), (4, 6, 7),        # z = z + d    (front)
    (0, 1, 5), (0, 5, 4),        # y = y        (bottom)
    (2, 3, 7), (2, 7, 6),        # y = y + h    (top)
    (1, 2, 6), (1, 6, 5),        # x = x + w    (right)
    (3, 0, 4), (3, 4, 7),        # x = x        (left)
]


def box_corners(box: dict) -> list[tuple[float, float, float]]:
    """The 8 corners of one box, from (x, y, z) to (x+w, y+h, z+d).

    Corner order is fixed: the four at z, counter-clockwise from (x, y), then
    the same four at z + d. CUBOID_FACES indexes this order.

    Args:
        box: A box dict from build_boxes().

    Returns:
        (x, y, z) triples in mm, in the export's own frame.
    """
    x, y, z = box["x"], box["y"], box["z"]
    x1, y1, z1 = x + box["w"], y + box["h"], z + box["d"]
    return [(x, y, z), (x1, y, z), (x1, y1, z), (x, y1, z),
            (x, y, z1), (x1, y, z1), (x1, y1, z1), (x, y1, z1)]


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


# The overview the view falls back to once the walk is over: every part at
# real size, coloured by what the run decided about it. These four strings
# mirror adjudicate.py's vocabulary; they are repeated rather than imported
# so this module has no opinion about how a verdict is reached, and a test
# pins them to adjudicate's own constants so the copy cannot drift.
#
# Chosen by simulating protanopia, deuteranopia and tritanopia (Machado 2009)
# and maximising the worst pairwise CIELAB separation over all four views:
# dE 16.7 at worst, against 7.1 for the obvious Okabe-Ito reading, where
# purple and grey collapse into each other for deuteranopes.
OVERVIEW_COLOURS = {
    "match": "#1F6FB2",              # blue
    "mismatch": "#E34A33",           # orange-red
    "abstain": "#FFB400",            # amber
    "not_in_schematic": "#762A83",   # purple
}
NOT_WALKED = "never visited"
NOT_WALKED_COLOUR = "#A6A6A6"        # grey
STRUCTURAL_LABEL = "structural"
STRUCTURAL_COLOUR = "#E3E3E3"        # faded: metalwork, not a result

# position.py picks which frame is which by location prefix and says so is
# UNVERIFIED. Every reading of this view inherits that, so it is on screen
# in both modes rather than in a docstring nobody opens.
FRAME_NOTE = "frame mapping unverified"


def structural_tags(path: Path = SCHEMATIC) -> frozenset:
    """The tags of the metalwork: DIN rails and wire ducts.

    Typed from position.py's STRUCTURAL rather than a tag-prefix rule, so
    there stays one definition of what counts as metalwork.

    Args:
        path: Cleaned schematic JSON.

    Returns:
        A frozenset of designations.
    """
    records = json.loads(Path(path).read_text(encoding="utf-8"))["components"]
    return frozenset(r["designation"] for r in records
                     if r["type"] in STRUCTURAL)


def outcome_groups(boxes: list[dict], results: frozenset,
                   structural: frozenset) -> list[dict]:
    """Split the boxes into the groups the overview legend lists.

    Counts are of tags, not boxes, so they are the run's own totals: a strip
    the run answered once counts once, though it is twenty boxes on screen.

    Args:
        boxes: Boxes from build_boxes().
        results: (tag, outcome) pairs the run has decided.
        structural: Tags of the metalwork.

    Returns:
        One dict per group, in legend order, with name, colour, boxes and
        count. Every group is present even when empty, so the legend always
        lists every outcome rather than only the ones that happened.
    """
    outcomes = dict(results)
    walked = [b for b in boxes if b["tag"] not in structural]
    groups = []
    for name, colour in OVERVIEW_COLOURS.items():
        members = [b for b in walked if outcomes.get(b["tag"]) == name]
        groups.append({"name": name, "colour": colour, "boxes": members,
                       "count": len({b["tag"] for b in members})})
    never = [b for b in walked if b["tag"] not in outcomes]
    groups.append({"name": NOT_WALKED, "colour": NOT_WALKED_COLOUR,
                   "boxes": never, "count": len({b["tag"] for b in never})})
    metal = [b for b in boxes if b["tag"] in structural]
    groups.append({"name": STRUCTURAL_LABEL, "colour": STRUCTURAL_COLOUR,
                   "boxes": metal, "count": len({b["tag"] for b in metal})})
    return groups


def legend_label(group: dict) -> str:
    """The legend entry for one group: its name and its count.

    Args:
        group: A group dict from outcome_groups().

    Returns:
        e.g. "match (12)".
    """
    return f"{group['name']} ({group['count']})"


def mesh_arrays(entries: list[tuple]) -> dict:
    """Flatten (box, colour, hover) triples into one Mesh3d trace's arrays.

    One merged trace rather than one per box, which keeps the browser
    responsive at 173 boxes.

    Args:
        entries: (box, colour, hover) triples.

    Returns:
        Dict of x/y/z vertex lists, i/j/k triangle indices, per-face colours
        and per-vertex hover text, in the export's own axes.
    """
    xs, ys, zs, text = [], [], [], []
    i, j, k, facecolour = [], [], [], []
    for n, (box, colour, hover) in enumerate(entries):
        for cx, cy, cz in box_corners(box):
            xs.append(cx)
            ys.append(cy)
            zs.append(cz)
            text.append(hover)
        offset = 8 * n
        for a, b, c in CUBOID_FACES:
            i.append(offset + a)
            j.append(offset + b)
            k.append(offset + c)
            facecolour.append(colour)
    return {"x": xs, "y": ys, "z": zs, "i": i, "j": j, "k": k,
            "facecolour": facecolour, "text": text}


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


def _apply_layout(figure, legend: bool) -> None:
    """Put the camera, the axes and the standing caveat on a figure.

    Plotly draws its z axis vertically, so the export's y is passed as the
    plot's z and the export's z (depth) as the plot's y. The data is not
    transformed -- only which screen axis each one is drawn on. aspectmode
    "data" keeps 1 mm the same length on every axis.

    The camera is orthographic and square on to the face. Depth runs toward
    the viewer, so the camera sits at +z, which is +y once y and z are
    swapped. Plotly puts +x to the LEFT from there, which would mirror the
    cabinet and reverse the walking order; reversing the x axis cancels it
    and keeps the tick labels true.

    Args:
        figure: The figure to lay out.
        legend: Whether to show the legend (the overview does, the walk
            does not -- during a walk there is nothing to key).
    """
    figure.update_layout(
        height=760,
        margin=dict(l=8, r=8, t=8, b=8),   # 0 clips the y tick labels
        showlegend=legend,
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01,
                    bgcolor="rgba(255,255,255,0.78)", borderwidth=0),
        scene=dict(
            aspectmode="data",                      # equal scaling, all axes
            xaxis=dict(title="x — across (mm)", autorange="reversed"),
            yaxis=dict(title="z — depth (mm)"),
            zaxis=dict(title="y — height (mm)"),
            camera=dict(
                eye=dict(x=0.0, y=2.5, z=0.0),      # out in front of the face
                center=dict(x=0.0, y=0.0, z=0.0),
                up=dict(x=0.0, y=0.0, z=1.0),       # export y, upright
                projection=dict(type="orthographic"),
            ),
        ),
        annotations=[dict(
            text=FRAME_NOTE, xref="paper", yref="paper",
            x=0.99, y=0.01, xanchor="right", yanchor="bottom",
            showarrow=False, font=dict(size=11), opacity=0.75,
        )],
    )


def build_figure(results: frozenset = frozenset(),
                 current: str | None = None,
                 boxes: list[dict] | None = None,
                 structural: frozenset | None = None):
    """The 3D view: a walk in progress, or the overview once it is over.

    With a current item the view is a walk: everything unread is a token
    cube, the current item is green, and what has been answered is drawn
    true. With no current item the walk is finished, so there is nothing
    left to give away and every part is drawn at real size, coloured by
    what the run decided, with a legend counting each outcome.

    Args:
        results: (tag, outcome) pairs the run has decided.
        current: Tag of the item the run is on, or None when the walk is
            over. This is what switches the two modes.
        boxes: Boxes to draw; built from the cleaned export if not given.
        structural: Metalwork tags; read from the export if not given.

    Returns:
        A plotly Figure.
    """
    import plotly.graph_objects as go       # lazy: the page guards the import

    boxes = build_boxes() if boxes is None else boxes
    structural = structural_tags() if structural is None else structural
    outcomes = dict(results)
    traces = []

    if current is None:                     # the walk is over: overview
        for group in outcome_groups(boxes, results, structural):
            mesh = mesh_arrays([
                (box, group["colour"],
                 f"{box['tag']} — {box['frame']}<br>{group['name']}")
                for box in group["boxes"]])
            traces.append(go.Mesh3d(
                x=mesh["x"], y=mesh["z"], z=mesh["y"],   # y upright
                i=mesh["i"], j=mesh["j"], k=mesh["k"],
                color=group["colour"],       # uniform, so the swatch is right
                text=mesh["text"], hoverinfo="text",
                flatshading=True, showlegend=True,
                name=legend_label(group), legendgroup=group["name"],
            ))
    else:
        green = representative_index(boxes, current)
        mesh = mesh_arrays([
            box_style(box, outcome=outcomes.get(box["tag"]),
                      structural=box["tag"] in structural,
                      current=n == green)
            for n, box in enumerate(boxes)])
        traces.append(go.Mesh3d(
            x=mesh["x"], y=mesh["z"], z=mesh["y"],       # y upright
            i=mesh["i"], j=mesh["j"], k=mesh["k"],
            facecolor=mesh["facecolour"],
            text=mesh["text"], hoverinfo="text",
            flatshading=True, showlegend=False,
        ))

    figure = go.Figure(data=traces)
    _apply_layout(figure, legend=current is None)
    return figure


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
