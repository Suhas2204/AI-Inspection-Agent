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
import math
from pathlib import Path

from ..paths import SCHEMATIC
from ..prep.position import DUCT_TYPES, RAIL_TYPE, STRUCTURAL
from ..prep.position import frame_of  # one definition of "which frame a part is in"

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
CURRENT_MM = 48.0
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


# --------------------------------------------------------------- appearance
# Looks only. Nothing below decides what is drawn or hidden -- box_style still
# owns that -- only how a thing already allowed on screen is shaped.
BODY_COLOUR = "#c3beb0"          # beige device bodies
METAL_COLOUR = "#aeb2b5"         # rails and ducts: metalwork, not a result
PLATE_COLOUR = "#9aa0a4"         # the mounting plate: mid grey
EDGE_COLOUR = "#44484b"          # the dark line around each drawn box
CABINET_LINE_COLOUR = "#9aa0a6"  # the cabinet wireframe
PLATE_THICKNESS_MM = 18.0
CABINET_PAD_MM = 60.0
PLATE_PAD_MM = 90.0              # plate margin: every rail sits well inside it
WALL_COLOUR = "#8a9096"          # the two side walls
WALL_THICKNESS_MM = 4.0          # the gap between frames is only 5 mm
FRAME_TINT = 0.13                # a tint, not a fill: the plate stays grey
CURRENT_HALO_COLOUR = "#5dff9b"  # the bright ring around the current item
CURRENT_HALO_SCALE = 1.7

# Square on to the face, and a three-quarter view for reading depth. Both
# orthographic: a rail has to stay straight in either.
FRONT_CAMERA = dict(
    eye=dict(x=0.0, y=2.5, z=0.0), center=dict(x=0.0, y=0.0, z=0.0),
    up=dict(x=0.0, y=0.0, z=1.0), projection=dict(type="orthographic"))
ANGLED_CAMERA = dict(
    eye=dict(x=-1.7, y=2.0, z=1.1), center=dict(x=0.0, y=0.0, z=0.0),
    up=dict(x=0.0, y=0.0, z=1.0), projection=dict(type="orthographic"))

SOFT_LIGHTING = dict(ambient=0.58, diffuse=0.62, specular=0.06,
                     roughness=0.92, fresnel=0.08)
LIGHT_POSITION = dict(x=1200, y=-600, z=2600)

STRIP_TAGS = ["-X1", "-X2", "-X3", "-X4", "-X5", "-X6", "-X7", "-X8"]


def part_types(path: Path = SCHEMATIC) -> dict:
    """Tag to part type, read from the cleaned export.

    build_boxes() deliberately returns six numbers and no type, so the shape
    lookup needs its own read.

    Args:
        path: Cleaned schematic JSON.

    Returns:
        Dict of designation to type string.
    """
    records = json.loads(Path(path).read_text(encoding="utf-8"))["components"]
    return {r["designation"]: r["type"] for r in records}


def part_kind(tag: str, part_type: str) -> str:
    """Which family of shape a part is drawn as.

    Args:
        tag: The part's designation.
        part_type: Its type string from the export.

    Returns:
        One of "rail", "duct", "terminal", "breaker", "relay", "other".
    """
    kind = (part_type or "").lower()
    if part_type == RAIL_TYPE:
        return "rail"
    if part_type in DUCT_TYPES:
        return "duct"
    if tag in STRIP_TAGS:
        return "terminal"
    if ("c60n" in kind or "ic40n" in kind or kind.startswith("fi,")
            or "ma, typ" in kind or "a-b/" in kind):
        return "breaker"
    if "relais" in kind or "relay" in kind or "vac" in kind or "4pol" in kind:
        return "relay"
    return "other"


def _cuboid(x0, y0, z0, x1, y1, z1) -> tuple:
    """One axis-aligned box as vertices and triangles.

    Args:
        x0, y0, z0: Low corner.
        x1, y1, z1: High corner.

    Returns:
        (vertices, triangles).
    """
    verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    return verts, list(CUBOID_FACES)


def _prism(profile: list, axis: str, lo: float, hi: float) -> tuple:
    """A convex cross-section extruded along one axis, with end caps.

    Args:
        profile: (u, v) points of a convex polygon, in order, in the two
            axes that are not `axis`.
        axis: "x", "y" or "z".
        lo: Where the extrusion starts along `axis`.
        hi: Where it ends.

    Returns:
        (vertices, triangles).
    """
    def point(u, v, w):
        if axis == "x":
            return (w, u, v)
        if axis == "y":
            return (u, w, v)
        return (u, v, w)

    n = len(profile)
    verts = ([point(u, v, lo) for u, v in profile]
             + [point(u, v, hi) for u, v in profile])
    tris = []
    for i in range(n):                       # sides
        j = (i + 1) % n
        tris.append((i, j, n + j))
        tris.append((i, n + j, n + i))
    for i in range(1, n - 1):                # caps: fan, convex only
        tris.append((0, i, i + 1))
        tris.append((n, n + i + 1, n + i))
    return verts, tris


def _ring(cx, cy, r, sides=10) -> list:
    """A regular polygon standing in for a circle.

    Args:
        cx, cy: Centre in the profile plane.
        r: Radius.
        sides: Number of sides.

    Returns:
        (u, v) points.
    """
    return [(cx + r * math.cos(2 * math.pi * i / sides),
             cy + r * math.sin(2 * math.pi * i / sides)) for i in range(sides)]


def _long_axis(box: dict) -> str:
    """Which axis a rail or duct runs along.

    Args:
        box: A box dict.

    Returns:
        "x", "y" or "z".
    """
    return max((("x", box["w"]), ("y", box["h"]), ("z", box["d"])),
               key=lambda pair: pair[1])[0]


def shape_pieces(box: dict, kind: str) -> list:
    """The solids a part is drawn as, all inside the part's own box.

    Every vertex is a fraction of the box passed in, so a shape can never
    report a size the part does not have. Nothing here decides whether to
    shape a part at all; the caller does that.

    Args:
        box: The box to fill, from build_boxes() or box_style().
        kind: A part_kind() value.

    Returns:
        List of (vertices, triangles, role, draw_edges), role being "body"
        or "accent".
    """
    x0, y0, z0 = box["x"], box["y"], box["z"]
    w, h, d = box["w"], box["h"], box["d"]
    x1, y1, z1 = x0 + w, y0 + h, z0 + d

    if kind == "rail":                        # top hat: raised web, flat lips
        if _long_axis(box) == "x":
            web = _cuboid(x0, y0 + 0.28 * h, z0, x1, y0 + 0.72 * h, z1)
            lo = _cuboid(x0, y0, z0, x1, y0 + 0.28 * h, z0 + 0.34 * d)
            hi = _cuboid(x0, y0 + 0.72 * h, z0, x1, y1, z0 + 0.34 * d)
        else:
            web = _cuboid(x0 + 0.28 * w, y0, z0, x0 + 0.72 * w, y1, z1)
            lo = _cuboid(x0, y0, z0, x0 + 0.28 * w, y1, z0 + 0.34 * d)
            hi = _cuboid(x0 + 0.72 * w, y0, z0, x1, y1, z0 + 0.34 * d)
        return [(web[0], web[1], "body", True),
                (lo[0], lo[1], "body", False),
                (hi[0], hi[1], "body", False)]

    if kind == "duct":                        # U channel, slotted at the front
        axis = _long_axis(box)
        back = _cuboid(x0, y0, z0, x1, y1, z0 + 0.30 * d)
        pieces = [(back[0], back[1], "body", True)]
        length = {"x": w, "y": h, "z": d}[axis]
        teeth = max(3, min(18, int(length / 55.0)))
        pitch = length / teeth
        start = {"x": x0, "y": y0, "z": z0}[axis]
        for n in range(teeth):
            a = start + n * pitch
            b = a + pitch * 0.58               # the gap between is the slot
            if axis == "x":
                walls = [_cuboid(a, y0, z0, b, y0 + 0.26 * h, z1),
                         _cuboid(a, y1 - 0.26 * h, z0, b, y1, z1)]
            elif axis == "y":
                walls = [_cuboid(x0, a, z0, x0 + 0.26 * w, b, z1),
                         _cuboid(x1 - 0.26 * w, a, z0, x1, b, z1)]
            else:
                walls = [_cuboid(x0, y0, a, x0 + 0.26 * w, y1, b),
                         _cuboid(x1 - 0.26 * w, y0, a, x1, y1, b)]
            for verts, tris in walls:
                pieces.append((verts, tris, "body", False))
        return pieces

    if kind == "terminal":                    # thin slab, two screw heads
        slab = _cuboid(x0, y0, z0, x1, y1, z0 + 0.78 * d)
        pieces = [(slab[0], slab[1], "body", True)]
        r = min(0.42 * w, 0.20 * h)
        for frac in (0.30, 0.70):
            verts, tris = _prism(_ring(x0 + 0.5 * w, y0 + frac * h, r),
                                 "z", z0 + 0.78 * d, z1)
            pieces.append((verts, tris, "accent", False))
        return pieces

    if kind == "breaker":                     # body, stepped front, toggle
        body = _cuboid(x0, y0, z0, x1, y1, z0 + 0.62 * d)
        step = _cuboid(x0, y0 + 0.10 * h, z0 + 0.62 * d,
                       x1, y1 - 0.10 * h, z0 + 0.90 * d)
        toggle = _cuboid(x0 + 0.34 * w, y0 + 0.38 * h, z0 + 0.90 * d,
                         x1 - 0.34 * w, y1 - 0.38 * h, z1)
        return [(body[0], body[1], "body", True),
                (step[0], step[1], "body", False),
                (toggle[0], toggle[1], "accent", False)]

    if kind == "relay":                       # body with a raised cover
        body = _cuboid(x0, y0, z0, x1, y1, z0 + 0.72 * d)
        cover = _cuboid(x0 + 0.12 * w, y0 + 0.12 * h, z0 + 0.72 * d,
                        x1 - 0.12 * w, y1 - 0.12 * h, z1)
        band = _cuboid(x0, y0 + 0.44 * h, z0 + 0.60 * d,
                       x1, y0 + 0.56 * h, z0 + 0.72 * d)
        return [(body[0], body[1], "body", True),
                (cover[0], cover[1], "body", False),
                (band[0], band[1], "accent", False)]

    chamfer = min(w, h) * 0.16                # anything else: eased edges
    profile = [
        (x0 + chamfer, y0), (x1 - chamfer, y0),
        (x1, y0 + chamfer), (x1, y1 - chamfer),
        (x1 - chamfer, y1), (x0 + chamfer, y1),
        (x0, y1 - chamfer), (x0, y0 + chamfer),
    ]
    verts, tris = _prism(profile, "z", z0, z1)
    return [(verts, tris, "body", True)]


def is_shaped(outcome: str | None, structural: bool,
              current: bool) -> bool:
    """Whether a part may be drawn as its real shape.

    Shaping follows the sizing rule and never leads it. A part still drawn
    as a token cube by box_style() must stay a cube here: an outline gives
    away as much as a size, and the current item is a destination, not a
    description.

    Args:
        outcome: The run's verdict for this tag, or None.
        structural: True for rails and ducts.
        current: True for the one box the run is sending the trainee to.

    Returns:
        True if the part may take its real shape.
    """
    return not current and (outcome is not None or structural)


def plain_cube_pieces(box: dict) -> list:
    """A box drawn as itself, with no shaping at all.

    What every unanswered part and the current item get, so that shape gives
    nothing away.

    Args:
        box: The box to draw.

    Returns:
        A single-piece list, shaped like shape_pieces() returns.
    """
    verts, tris = _cuboid(box["x"], box["y"], box["z"],
                          box["x"] + box["w"], box["y"] + box["h"],
                          box["z"] + box["d"])
    return [(verts, tris, "body", True)]


def pieces_mesh(entries: list) -> dict:
    """Flatten shaped parts into one Mesh3d trace's arrays.

    Args:
        entries: (pieces, body_colour, accent_colour, hover) tuples.

    Returns:
        Dict of x/y/z, i/j/k, facecolour and text, in the export's own axes.
    """
    xs, ys, zs, text = [], [], [], []
    i, j, k, facecolour = [], [], [], []
    for pieces, body, accent, hover in entries:
        for verts, tris, role, _edges in pieces:
            offset = len(xs)
            for vx, vy, vz in verts:
                xs.append(vx)
                ys.append(vy)
                zs.append(vz)
                text.append(hover)
            colour = body if role == "body" else accent
            for a, b, c in tris:
                i.append(offset + a)
                j.append(offset + b)
                k.append(offset + c)
                facecolour.append(colour)
    return {"x": xs, "y": ys, "z": zs, "i": i, "j": j, "k": k,
            "facecolour": facecolour, "text": text}


def _box_edge_points(box: dict) -> tuple:
    """The 12 edges of one box as a broken line.

    Args:
        box: The box to outline.

    Returns:
        (xs, ys, zs) with None between segments.
    """
    c = box_corners(box)
    pairs = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
             (0, 4), (1, 5), (2, 6), (3, 7)]
    xs, ys, zs = [], [], []
    for a, b in pairs:
        xs += [c[a][0], c[b][0], None]
        ys += [c[a][1], c[b][1], None]
        zs += [c[a][2], c[b][2], None]
    return xs, ys, zs


def extents(boxes: list) -> dict:
    """The overall bounding box of every part, in mm.

    Args:
        boxes: Boxes from build_boxes().

    Returns:
        Dict with x0/x1/y0/y1/z0/z1.
    """
    return {
        "x0": min(b["x"] for b in boxes),
        "x1": max(b["x"] + b["w"] for b in boxes),
        "y0": min(b["y"] for b in boxes),
        "y1": max(b["y"] + b["h"] for b in boxes),
        "z0": min(b["z"] for b in boxes),
        "z1": max(b["z"] + b["d"] for b in boxes),
    }


def blend(colour: str, other: str, amount: float) -> str:
    """Mix two hex colours.

    Args:
        colour: The colour to mix in.
        other: The base colour.
        amount: How much of `colour` to take, 0 to 1.

    Returns:
        A hex colour.
    """
    a = [int(colour[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * amount + y * (1 - amount)):02x}"
                         for x, y in zip(a, b))


def frame_regions(boxes: list) -> list:
    """The patch of plate each mounting frame occupies, tinted.

    Only the two mounting frames get a region: a side panel's parts sit
    inside its frame's own x span, so a second patch there would z-fight
    with the first. The side panels are shown by their walls instead.

    Args:
        boxes: Boxes from build_boxes().

    Returns:
        List of dicts with frame, colour and box.
    """
    pad = PLATE_PAD_MM * 0.45
    spans = []
    for frame in ("left frame", "right frame"):
        members = [b for b in boxes if b["frame"] == frame]
        if members:
            spans.append([frame,
                          min(b["x"] for b in members),
                          max(b["x"] + b["w"] for b in members),
                          min(b["y"] for b in members) - pad,
                          max(b["y"] + b["h"] for b in members) + pad])
    spans.sort(key=lambda r: r[1])

    # Pad outward freely, but never past halfway to the next frame: the gap
    # between the two frames is 5 mm, and two patches at one depth flicker.
    edges = []
    for n, (_f, lo, hi, _y0, _y1) in enumerate(spans):
        left = lo - pad if n == 0 else (spans[n - 1][2] + lo) / 2.0
        right = (hi + spans[n + 1][1]) / 2.0 if n + 1 < len(spans) else hi + pad
        edges.append((left, right))

    z0 = min(b["z"] for b in boxes)
    regions = []
    for (frame, _lo, _hi, y0, y1), (x0, x1) in zip(spans, edges):
        regions.append({
            "frame": frame,
            "colour": blend(FRAME_COLOURS[frame], PLATE_COLOUR, FRAME_TINT),
            "box": {"tag": "", "frame": frame, "x": x0, "y": y0,
                    "z": z0 - 2.0, "w": x1 - x0, "h": y1 - y0, "d": 2.0},
        })
    return regions


def side_walls(boxes: list) -> list:
    """A wall at the outer edge of each side panel, touching its parts.

    The side-panel parts are a column of ducts at the right-hand edge of
    their frame, so the wall goes immediately outboard of them and they meet
    it. Nothing is moved to make that true -- the wall is placed where the
    parts already are.

    Args:
        boxes: Boxes from build_boxes().

    Returns:
        List of dicts with frame, colour and box.
    """
    walls = []
    for frame in ("left side panel", "right side panel"):
        members = [b for b in boxes if b["frame"] == frame]
        if not members:
            continue
        x1 = max(b["x"] + b["w"] for b in members)
        y0 = min(b["y"] for b in boxes)
        y1 = max(b["y"] + b["h"] for b in boxes)
        z0 = min(b["z"] for b in boxes)
        z1 = max(b["z"] + b["d"] for b in boxes)
        walls.append({
            "frame": frame,
            "colour": blend(FRAME_COLOURS[frame], WALL_COLOUR, FRAME_TINT),
            "box": {"tag": "", "frame": frame, "x": x1, "y": y0, "z": z0,
                    "w": WALL_THICKNESS_MM, "h": y1 - y0, "d": z1 - z0},
        })
    return walls


def halo_box(box: dict) -> dict:
    """A box around the current item, bigger than it, for the bright ring.

    The ring is the same size for every item, so it marks a place without
    reporting a size.

    Args:
        box: The current item's drawn cube.

    Returns:
        A box dict to draw as lines.
    """
    return centred_cube(box, max(box["w"], box["h"], box["d"])
                        * CURRENT_HALO_SCALE)


def mounting_plate(boxes: list) -> dict:
    """A light grey plate sitting behind every part.

    Args:
        boxes: Boxes from build_boxes().

    Returns:
        A box dict for the plate.
    """
    e = extents(boxes)
    pad = PLATE_PAD_MM
    walls = side_walls(boxes)
    x1 = max([e["x1"]] + [w["box"]["x"] + w["box"]["w"] for w in walls])
    return {"tag": "", "frame": "",
            "x": e["x0"] - pad, "y": e["y0"] - pad,
            "z": e["z0"] - PLATE_THICKNESS_MM,
            "w": (x1 - e["x0"]) + 2 * pad,
            "h": (e["y1"] - e["y0"]) + 2 * pad,
            "d": PLATE_THICKNESS_MM}


def cabinet_outline(boxes: list) -> dict:
    """The wireframe box around the whole cabinet.

    Args:
        boxes: Boxes from build_boxes().

    Returns:
        A box dict to be drawn as lines, not as a solid.
    """
    e = extents(boxes)
    pad = CABINET_PAD_MM
    return {"tag": "", "frame": "",
            "x": e["x0"] - pad, "y": e["y0"] - pad,
            "z": e["z0"] - PLATE_THICKNESS_MM - pad * 0.25,
            "w": (e["x1"] - e["x0"]) + 2 * pad,
            "h": (e["y1"] - e["y0"]) + 2 * pad,
            "d": (e["z1"] - e["z0"]) + PLATE_THICKNESS_MM + pad * 0.5}


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
            camera=FRONT_CAMERA,               # the view opens square on
        ),
        updatemenus=[dict(
            type="buttons", direction="left", showactive=True,
            x=0.01, y=0.99, xanchor="left", yanchor="bottom",
            pad=dict(r=4, t=4), bgcolor="rgba(255,255,255,0.8)",
            buttons=[
                dict(label="Front view", method="relayout",
                     args=[{"scene.camera": FRONT_CAMERA}]),
                dict(label="Angled view", method="relayout",
                     args=[{"scene.camera": ANGLED_CAMERA}]),
            ])],
        annotations=[dict(
            text=FRAME_NOTE, xref="paper", yref="paper",
            x=0.99, y=0.01, xanchor="right", yanchor="bottom",
            showarrow=False, font=dict(size=11), opacity=0.75,
        )],
    )


def _mesh3d(go, mesh, **kwargs):
    """One Mesh3d with this view's shading settings.

    Args:
        go: plotly.graph_objects.
        mesh: Arrays from pieces_mesh().
        **kwargs: Passed through to Mesh3d.

    Returns:
        A Mesh3d trace.
    """
    return go.Mesh3d(
        x=mesh["x"], y=mesh["z"], z=mesh["y"],       # y upright, z into depth
        i=mesh["i"], j=mesh["j"], k=mesh["k"],
        flatshading=False, lighting=SOFT_LIGHTING,
        lightposition=LIGHT_POSITION, **kwargs)


def _lines(go, boxes, colour, width, name=None):
    """A Scatter3d of box outlines.

    Args:
        go: plotly.graph_objects.
        boxes: Boxes to outline.
        colour: Line colour.
        width: Line width.
        name: Trace name, if any.

    Returns:
        A Scatter3d trace.
    """
    xs, ys, zs = [], [], []
    for box in boxes:
        bx, by, bz = _box_edge_points(box)
        xs += bx
        ys += by
        zs += bz
    return go.Scatter3d(
        x=xs, y=zs, z=ys,                            # same axis swap
        mode="lines", line=dict(color=colour, width=width),
        hoverinfo="skip", showlegend=False, name=name or "")


def build_figure(results: frozenset = frozenset(),
                 current: str | None = None,
                 boxes: list[dict] | None = None,
                 structural: frozenset | None = None,
                 types: dict | None = None):
    """The 3D view: a walk in progress, or the overview once it is over.

    With a current item the view is a walk: everything unread is a plain
    token cube, the current item is a plain green cube, and only what has
    been answered is shaped. With no current item the walk is finished, so
    there is nothing left to give away and every part is drawn at real size,
    shaped, and coloured by what the run decided.

    Shaping follows the same rule as sizing and never leads it: a part that
    is still a cube under box_style() stays a cube here, because an outline
    is as much of a giveaway as a size.

    Args:
        results: (tag, outcome) pairs the run has decided.
        current: Tag of the item the run is on, or None once the walk is
            over. This is what switches the two modes.
        boxes: Boxes to draw; built from the cleaned export if not given.
        structural: Metalwork tags; read from the export if not given.
        types: Tag to part type; read from the export if not given.

    Returns:
        A plotly Figure.
    """
    import plotly.graph_objects as go       # lazy: the page guards the import

    boxes = build_boxes() if boxes is None else boxes
    structural = structural_tags() if structural is None else structural
    types = part_types() if types is None else types
    outcomes = dict(results)

    plate = mounting_plate(boxes)
    traces = [_mesh3d(go, pieces_mesh([(plain_cube_pieces(plate),
                                        PLATE_COLOUR, PLATE_COLOUR, "")]),
                      color=PLATE_COLOUR, hoverinfo="skip", showlegend=False,
                      name="plate")]
    for region in frame_regions(boxes):          # which frame is which, faintly
        traces.append(_mesh3d(
            go, pieces_mesh([(plain_cube_pieces(region["box"]),
                              region["colour"], region["colour"], "")]),
            color=region["colour"], hoverinfo="skip", showlegend=False,
            name="frame tint"))
    for wall in side_walls(boxes):               # the side panels stand on these
        traces.append(_mesh3d(
            go, pieces_mesh([(plain_cube_pieces(wall["box"]),
                              wall["colour"], wall["colour"], "")]),
            color=wall["colour"], hoverinfo="skip", showlegend=False,
            name="side wall"))
    outlined = []
    halo = None

    if current is None:                     # the walk is over: overview
        for group in outcome_groups(boxes, results, structural):
            entries = []
            for box in group["boxes"]:
                kind = part_kind(box["tag"], types.get(box["tag"], ""))
                entries.append((shape_pieces(box, kind), group["colour"],
                                group["colour"],
                                f"{box['tag']} — {box['frame']}<br>"
                                f"{group['name']}"))
                outlined.append(box)
            traces.append(_mesh3d(go, pieces_mesh(entries),
                                  color=group["colour"],
                                  text=pieces_mesh(entries)["text"],
                                  hoverinfo="text", showlegend=True,
                                  name=legend_label(group),
                                  legendgroup=group["name"]))
    else:
        green = representative_index(boxes, current)
        entries = []
        for n, box in enumerate(boxes):
            is_structural = box["tag"] in structural
            outcome = outcomes.get(box["tag"])
            drawn, colour, hover = box_style(box, outcome=outcome,
                                             structural=is_structural,
                                             current=n == green)
            shaped = is_shaped(outcome, is_structural, n == green)
            if shaped:
                kind = part_kind(box["tag"], types.get(box["tag"], ""))
                pieces = shape_pieces(drawn, kind)
                body = METAL_COLOUR if is_structural else BODY_COLOUR
                accent = (METAL_COLOUR if is_structural
                          else FRAME_COLOURS.get(box["frame"],
                                                 UNKNOWN_FRAME_COLOUR))
            else:
                pieces = plain_cube_pieces(drawn)
                body = accent = colour
            if n == green:
                halo = halo_box(drawn)
            entries.append((pieces, body, accent, hover))
            outlined.append(drawn)
        mesh = pieces_mesh(entries)
        traces.append(_mesh3d(go, mesh, facecolor=mesh["facecolour"],
                              text=mesh["text"], hoverinfo="text",
                              showlegend=False, name="parts"))

    traces.append(_lines(go, outlined, EDGE_COLOUR, 1))
    traces.append(_lines(go, [cabinet_outline(boxes)], CABINET_LINE_COLOUR, 2))
    if halo is not None:
        traces.append(_lines(go, [halo], CURRENT_HALO_COLOUR, 6, "halo"))

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
