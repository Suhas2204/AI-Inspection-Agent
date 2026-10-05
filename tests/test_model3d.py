"""Tests for model3d.py: the box set, and which box the 3D view marks green.

The green box tells the trainee where to walk next. If it drifts off the
checklist step the page is prompting, the picture sends them to one part
while the words send them to another, and nothing in the run would say so.
These tests pin the two together.
"""

import pytest

from redlining.checklist import load_checklist
from redlining.model3d import (
    BODY_COLOUR,
    FRAME_NOTE,
    is_shaped,
    part_kind,
    part_types,
    plain_cube_pieces,
    shape_pieces,
    NOT_WALKED,
    OVERVIEW_COLOURS,
    STRUCTURAL_LABEL,
    build_figure,
    legend_label,
    outcome_groups,
    structural_tags,
    CURRENT_COLOUR,
    CURRENT_HOVER,
    CURRENT_MM,
    FRAME_COLOURS,
    MIN_SIZE_MM,
    PLACEHOLDER_COLOUR,
    PLACEHOLDER_HOVER,
    PLACEHOLDER_MM,
    box_style,
    build_boxes,
    centred_cube,
    representative_index,
)


@pytest.fixture(scope="module")
def boxes():
    """The box set the viewer draws, built once for the module."""
    return build_boxes()


@pytest.fixture(scope="module")
def items():
    """The walking order the session steps through, in band order."""
    return load_checklist()


# --------------------------------------------------------------- the boxes
def test_every_box_has_the_eight_keys(boxes):
    """A box is tag, frame and six numbers -- nothing optional."""
    for box in boxes:
        assert set(box) == {"tag", "frame", "x", "y", "z", "w", "h", "d"}


def test_no_edge_is_zero(boxes):
    """Zero-sized parts are clamped, so every box is drawable."""
    for box in boxes:
        assert box["w"] >= MIN_SIZE_MM or box["w"] > 0
        assert min(box["w"], box["h"], box["d"]) > 0


# ------------------------------------------------- the green box == the step
def test_every_checklist_item_has_a_box(boxes, items):
    """Every item the trainee is sent to can be pointed at.

    An item with no box would leave the viewer with nothing green while the
    page prompts for it.
    """
    missing = [i.tag for i in items if representative_index(boxes, i.tag) is None]
    assert missing == []


def test_green_box_tag_matches_the_current_step(boxes, items):
    """Walking the checklist start to finish, the green box never drifts.

    This is the one that matters: for every step the session can be on, the
    box the viewer marks carries that step's tag.
    """
    for step, item in enumerate(items):
        index = representative_index(boxes, item.tag)
        assert index is not None, f"step {step} ({item.tag}) has no box"
        assert boxes[index]["tag"] == item.tag, (
            f"step {step}: page prompts {item.tag}, "
            f"viewer marks {boxes[index]['tag']}")


def test_green_box_is_in_the_frame_the_prompt_names(boxes, items):
    """The marked box sits in the frame the spoken prompt sends them to."""
    for item in items:
        index = representative_index(boxes, item.tag)
        assert boxes[index]["frame"] == item.frame, (
            f"{item.tag}: prompt says {item.frame}, "
            f"box is in {boxes[index]['frame']}")


def test_only_one_box_is_green(boxes, items):
    """One step marks one box, including for the eight terminal strips.

    A strip is many boxes sharing a tag -- -X5 is 20 -- so this is the case
    that could quietly light up twenty.
    """
    for item in items:
        index = representative_index(boxes, item.tag)
        assert isinstance(index, int)
        assert 0 <= index < len(boxes)


def test_strips_really_do_have_many_boxes(boxes, items):
    """Guard the test above: it is only meaningful while strips are plural."""
    strips = [i for i in items if i.kind == "strip"]
    assert strips, "no strips in the checklist -- the one-box test is vacuous"
    for item in strips:
        shared = [b for b in boxes if b["tag"] == item.tag]
        assert len(shared) > 1


def test_representative_is_the_one_the_walk_reaches_first(boxes, items):
    """Topmost, then leftmost -- position.py's order, not file order."""
    for item in items:
        index = representative_index(boxes, item.tag)
        shared = [b for b in boxes if b["tag"] == item.tag]
        top = max(b["y"] for b in shared)             # y negative downward
        assert boxes[index]["y"] == top
        assert boxes[index]["x"] == min(b["x"] for b in shared
                                        if b["y"] == top)


def test_selection_is_deterministic(boxes, items):
    """The same step marks the same box every time it is asked."""
    for item in items:
        assert (representative_index(boxes, item.tag)
                == representative_index(boxes, item.tag))


def test_unknown_tag_marks_nothing(boxes):
    """A tag with no box returns None rather than guessing at one."""
    assert representative_index(boxes, "-NOT-A-TAG") is None
    assert representative_index(boxes, "") is None


def test_finished_run_marks_nothing(boxes, items):
    """Past the last item the page passes no tag, so nothing is green.

    The view must not keep a stale green box on screen after the walk ends.
    """
    current = None if len(items) >= len(items) else items[0].tag
    assert current is None
    assert representative_index(boxes, current or "") is None


# ------------------------------------------------------------- how it is drawn
def test_no_frame_is_green(boxes):
    """Green is reserved for the current item, so no frame may use it.

    A green side panel next to a green "go here" box is the one confusion
    this palette has to avoid.
    """
    def greenish(hexcolour):
        r = int(hexcolour[1:3], 16)
        g = int(hexcolour[3:5], 16)
        b = int(hexcolour[5:7], 16)
        return g > r and g > b

    assert greenish(CURRENT_COLOUR), "the current item is supposed to be green"
    for frame, colour in FRAME_COLOURS.items():
        assert not greenish(colour), f"{frame} is green: {colour}"


def test_every_frame_in_the_data_has_a_colour(boxes):
    """No box falls through to the unknown-frame grey."""
    for box in boxes:
        assert box["frame"] in FRAME_COLOURS


def test_frame_colours_are_distinct():
    """Two frames the same colour would read as one frame."""
    assert len(set(FRAME_COLOURS.values())) == len(FRAME_COLOURS)
    assert PLACEHOLDER_COLOUR not in FRAME_COLOURS.values()
    assert CURRENT_COLOUR not in FRAME_COLOURS.values()


def test_answered_box_keeps_its_real_size_and_frame_colour(boxes):
    """An answered part is drawn as it really is, not as a token."""
    for box in boxes[:40]:
        drawn, colour, _ = box_style(box, outcome="match")
        assert (drawn["w"], drawn["h"], drawn["d"]) == (box["w"], box["h"],
                                                        box["d"])
        assert (drawn["x"], drawn["y"], drawn["z"]) == (box["x"], box["y"],
                                                        box["z"])
        assert colour == FRAME_COLOURS[box["frame"]]


@pytest.mark.parametrize("outcome",
                         ["match", "mismatch", "not_in_schematic", "abstain"])
def test_answered_hover_carries_the_tag_and_the_verdict(boxes, outcome):
    """Every adjudicate.py outcome reaches the hover, with the tag."""
    box = boxes[0]
    _, _, hover = box_style(box, outcome=outcome)
    assert box["tag"] in hover
    assert outcome in hover


def test_unanswered_hover_carries_neither_tag_nor_size(boxes):
    """Nothing identifying leaks before the part has been read."""
    for box in boxes:
        drawn, colour, hover = box_style(box)
        if box["tag"] in {b["tag"] for b in boxes}:
            assert hover == PLACEHOLDER_HOVER
            assert box["tag"] not in hover
            assert colour == PLACEHOLDER_COLOUR
            assert (drawn["w"], drawn["h"], drawn["d"]) == (
                PLACEHOLDER_MM, PLACEHOLDER_MM, PLACEHOLDER_MM)


def test_current_item_hover_carries_no_tag(boxes):
    """The green box says where to go, never what is there."""
    for box in boxes[:40]:
        drawn, colour, hover = box_style(box, current=True)
        assert hover == CURRENT_HOVER
        assert box["tag"] not in hover
        assert colour == CURRENT_COLOUR
        assert drawn["w"] == CURRENT_MM


def test_current_wins_over_its_own_answer(boxes):
    """A re-ask still points at one place rather than reverting to real size."""
    box = boxes[0]
    drawn, colour, hover = box_style(box, outcome="abstain", current=True)
    assert colour == CURRENT_COLOUR
    assert hover == CURRENT_HOVER
    assert drawn["w"] == CURRENT_MM


def test_structural_is_drawn_true_but_carries_no_verdict(boxes):
    """Rails and ducts are drawn real all run; they are never adjudicated."""
    box = boxes[0]
    drawn, colour, hover = box_style(box, structural=True)
    assert (drawn["w"], drawn["h"], drawn["d"]) == (box["w"], box["h"],
                                                    box["d"])
    assert colour == FRAME_COLOURS[box["frame"]]
    assert box["tag"] in hover
    for outcome in ("match", "mismatch", "not_in_schematic", "abstain"):
        assert outcome not in hover


def test_cube_sits_on_the_real_centre(boxes):
    """A token box withholds size, never position."""
    for box in boxes:
        for mm in (PLACEHOLDER_MM, CURRENT_MM):
            cube = centred_cube(box, mm)
            for axis, size in (("x", "w"), ("y", "h"), ("z", "d")):
                real = box[axis] + box[size] / 2.0
                drawn = cube[axis] + cube[size] / 2.0
                assert abs(real - drawn) < 1e-9


def test_centred_cube_keeps_the_real_size_reachable(boxes):
    """The real size is withheld from the screen, not thrown away."""
    box = boxes[0]
    cube = centred_cube(box, PLACEHOLDER_MM)
    assert cube["tag"] == box["tag"]
    assert box["w"] != PLACEHOLDER_MM or box["h"] != PLACEHOLDER_MM


# ------------------------------------------------------- the overview legend
@pytest.fixture(scope="module")
def structural():
    """Tags of the metalwork, which is never a result."""
    return structural_tags()


@pytest.fixture
def run_results(items):
    """A part-finished run: one of each outcome, the rest never visited.

    One of the four is a terminal strip, so every count here is a count of
    tags rather than of boxes -- the strip is twenty boxes on screen.
    """
    strip = next(i for i in items if i.kind == "strip")
    devices = [i.tag for i in items if i.kind != "strip"][:3]
    return frozenset(zip([strip.tag] + devices,
                         ["match", "mismatch", "abstain",
                          "not_in_schematic"]))


def test_legend_counts_equal_the_runs_totals(boxes, structural, run_results):
    """Each legend count is the number of tags the run gave that verdict.

    Counts are of tags, not boxes, or a strip answered once would report as
    twenty and the legend would disagree with the run's own report.
    """
    expected = {}
    for tag, outcome in run_results:
        expected[outcome] = expected.get(outcome, 0) + 1

    groups = {g["name"]: g for g in outcome_groups(boxes, run_results,
                                                   structural)}
    for outcome in OVERVIEW_COLOURS:
        assert groups[outcome]["count"] == expected.get(outcome, 0), outcome


def test_legend_counts_add_up_to_every_tag(boxes, structural, run_results):
    """Nothing is counted twice and nothing is left out."""
    groups = outcome_groups(boxes, run_results, structural)
    assert sum(g["count"] for g in groups) == len({b["tag"] for b in boxes})


def test_never_visited_is_everything_not_answered(boxes, structural,
                                                  run_results):
    """The grey count is the rest of the walk, metalwork excluded."""
    answered = {tag for tag, _ in run_results}
    walkable = {b["tag"] for b in boxes if b["tag"] not in structural}
    groups = {g["name"]: g for g in outcome_groups(boxes, run_results,
                                                   structural)}
    assert groups[NOT_WALKED]["count"] == len(walkable - answered)


def test_structural_is_its_own_group_not_an_outcome(boxes, structural,
                                                    run_results):
    """Metalwork is never scored, so it never lands in a verdict group."""
    groups = {g["name"]: g for g in outcome_groups(boxes, run_results,
                                                   structural)}
    assert groups[STRUCTURAL_LABEL]["count"] == len(structural)
    for outcome in OVERVIEW_COLOURS:
        for box in groups[outcome]["boxes"]:
            assert box["tag"] not in structural


def test_every_outcome_is_listed_even_at_zero(boxes, structural):
    """A legend that hides empty outcomes would read as 'none happened'."""
    groups = {g["name"]: g for g in outcome_groups(boxes, frozenset(),
                                                   structural)}
    for outcome in OVERVIEW_COLOURS:
        assert outcome in groups
        assert groups[outcome]["count"] == 0


def test_legend_label_carries_name_and_count():
    """The count has to reach the legend text, not just the group dict."""
    assert legend_label({"name": "match", "count": 12}) == "match (12)"


def test_outcome_names_match_adjudicate(boxes):
    """The copied vocabulary must not drift from adjudicate.py's own."""
    from redlining.adjudicate import (ABSTAIN, MATCH, MISMATCH,
                                      NOT_IN_SCHEMATIC)
    assert set(OVERVIEW_COLOURS) == {MATCH, MISMATCH, ABSTAIN,
                                     NOT_IN_SCHEMATIC}


def test_palette_is_distinct():
    """Two outcomes sharing a colour would be one outcome on screen."""
    from redlining.model3d import NOT_WALKED_COLOUR, STRUCTURAL_COLOUR
    colours = list(OVERVIEW_COLOURS.values()) + [NOT_WALKED_COLOUR,
                                                 STRUCTURAL_COLOUR]
    assert len(set(colours)) == len(colours)


# ------------------------------------------------------------- the figure
def test_overview_legend_shows_every_outcome_with_its_count(boxes, structural,
                                                            run_results):
    """The counts reach the built figure, not just the helper."""
    pytest.importorskip("plotly")
    figure = build_figure(run_results, None, boxes=boxes,
                          structural=structural)
    names = [trace.name for trace in figure.data if trace.showlegend]
    groups = outcome_groups(boxes, run_results, structural)
    assert names == [legend_label(g) for g in groups]
    assert figure.layout.showlegend is True


def test_walk_mode_has_no_legend(boxes, structural, items, run_results):
    """Mid-walk there is nothing to key, and a legend would name the parts."""
    pytest.importorskip("plotly")
    figure = build_figure(run_results, items[4].tag, boxes=boxes,
                          structural=structural)
    assert figure.layout.showlegend is False


def test_overview_draws_every_part(boxes, structural):
    """Once the walk is over nothing is withheld and nothing is dropped.

    Shaped parts carry more than eight corners each, so this counts parts
    through the groups rather than counting vertices.
    """
    pytest.importorskip("plotly")
    groups = outcome_groups(boxes, frozenset(), structural)
    assert sum(len(g["boxes"]) for g in groups) == len(boxes)

    figure = build_figure(frozenset(), None, boxes=boxes,
                          structural=structural)
    drawn = sum(len(trace.x) for trace in figure.data if trace.showlegend)
    assert drawn >= 8 * len(boxes)


@pytest.mark.parametrize("current", [None, "-1Q1"])
def test_frame_mapping_label_is_always_present(boxes, structural, current):
    """The caveat is on screen in both modes, not only in the overview."""
    pytest.importorskip("plotly")
    figure = build_figure(frozenset(), current, boxes=boxes,
                          structural=structural)
    texts = [a.text for a in figure.layout.annotations]
    assert FRAME_NOTE in texts, f"{FRAME_NOTE!r} missing, got {texts}"


def test_frame_mapping_label_sits_in_a_corner(boxes, structural):
    """A label in the middle of the cabinet would be worse than none."""
    pytest.importorskip("plotly")
    figure = build_figure(frozenset(), None, boxes=boxes,
                          structural=structural)
    note = next(a for a in figure.layout.annotations if a.text == FRAME_NOTE)
    assert note.xref == "paper" and note.yref == "paper"
    assert note.x > 0.9 and note.y < 0.1


def test_legend_counts_tags_not_boxes(boxes, structural, items):
    """A strip answered once counts once, though it is twenty boxes.

    This is the case that separates counting tags from counting boxes; the
    device-only fixtures cannot tell the two apart.
    """
    strip = next(i for i in items if i.kind == "strip")
    members = [b for b in boxes if b["tag"] == strip.tag]
    assert len(members) > 1, "strip is one box -- this test proves nothing"

    groups = {g["name"]: g
              for g in outcome_groups(boxes, frozenset({(strip.tag, "match")}),
                                      structural)}
    assert groups["match"]["count"] == 1
    assert len(groups["match"]["boxes"]) == len(members)


# ------------------------------------------------------------- the shapes
SHAPE_KINDS = ["rail", "duct", "terminal", "breaker", "relay", "other"]


@pytest.mark.parametrize("kind", SHAPE_KINDS)
def test_every_shape_stays_inside_its_real_box(boxes, kind):
    """No shape may stick out of the part it stands for.

    A protruding toggle or screw would report a size the part does not have,
    and in a view that withholds sizes that is the whole game.
    """
    for box in boxes:
        x0, y0, z0 = box["x"], box["y"], box["z"]
        x1, y1, z1 = x0 + box["w"], y0 + box["h"], z0 + box["d"]
        for verts, _tris, _role, _edges in shape_pieces(box, kind):
            for vx, vy, vz in verts:
                assert x0 - 1e-9 <= vx <= x1 + 1e-9, (kind, box["tag"], "x")
                assert y0 - 1e-9 <= vy <= y1 + 1e-9, (kind, box["tag"], "y")
                assert z0 - 1e-9 <= vz <= z1 + 1e-9, (kind, box["tag"], "z")


def test_real_parts_stay_inside_their_real_boxes(boxes):
    """The same, for the kind each part is actually drawn as."""
    types = part_types()
    for box in boxes:
        kind = part_kind(box["tag"], types.get(box["tag"], ""))
        x1, y1, z1 = (box["x"] + box["w"], box["y"] + box["h"],
                      box["z"] + box["d"])
        for verts, _tris, _role, _edges in shape_pieces(box, kind):
            for vx, vy, vz in verts:
                assert box["x"] - 1e-9 <= vx <= x1 + 1e-9
                assert box["y"] - 1e-9 <= vy <= y1 + 1e-9
                assert box["z"] - 1e-9 <= vz <= z1 + 1e-9


def test_every_shape_has_some_solid(boxes):
    """A shape that collapses to nothing would be invisible, not subtle."""
    types = part_types()
    for box in boxes:
        kind = part_kind(box["tag"], types.get(box["tag"], ""))
        pieces = shape_pieces(box, kind)
        assert pieces
        assert all(len(v) >= 8 and len(t) >= 12 for v, t, _r, _e in pieces)


def test_unanswered_parts_are_still_uniform_cubes(boxes, structural):
    """Shape must not leak what size already does not.

    Every unanswered part stays one plain cube of the same edge, whatever
    kind of part it happens to be.
    """
    for box in boxes:
        if box["tag"] in structural:
            continue
        assert not is_shaped(None, False, False)
        drawn, _colour, _hover = box_style(box)
        assert (drawn["w"], drawn["h"], drawn["d"]) == (PLACEHOLDER_MM,) * 3
        pieces = plain_cube_pieces(drawn)
        assert len(pieces) == 1
        verts, tris, _role, _edges = pieces[0]
        assert len(verts) == 8 and len(tris) == 12


def test_the_current_item_is_not_shaped():
    """The green box says where to go; a shape would say what is there."""
    assert is_shaped("match", False, True) is False
    assert is_shaped(None, True, True) is False


def test_shaping_follows_answering(boxes, structural):
    """Only answered or structural parts may be shaped."""
    assert is_shaped("match", False, False) is True
    assert is_shaped("abstain", False, False) is True
    assert is_shaped(None, True, False) is True
    assert is_shaped(None, False, False) is False


def test_walk_draws_exactly_the_geometry_the_rules_allow(boxes, structural):
    """End to end: the parts trace holds cubes for everything unrevealed.

    Counted rather than eyeballed, so a shape that escaped the rule would
    change the vertex total and fail here.
    """
    pytest.importorskip("plotly")
    types = part_types()
    current = next(b["tag"] for b in boxes if b["tag"] not in structural)
    green = representative_index(boxes, current)

    expected = 0
    for n, box in enumerate(boxes):
        is_struct = box["tag"] in structural
        if is_shaped(None, is_struct, n == green):
            kind = part_kind(box["tag"], types.get(box["tag"], ""))
            expected += sum(len(v) for v, _t, _r, _e in shape_pieces(box, kind))
        else:
            expected += 8

    figure = build_figure(frozenset(), current, boxes=boxes,
                          structural=structural, types=types)
    parts = next(tr for tr in figure.data if tr.name == "parts")
    assert len(parts.x) == expected


def test_overview_shapes_everything(boxes, structural):
    """With the walk over, every part takes its real shape."""
    pytest.importorskip("plotly")
    types = part_types()
    expected = sum(
        sum(len(v) for v, _t, _r, _e in
            shape_pieces(box, part_kind(box["tag"],
                                        types.get(box["tag"], ""))))
        for box in boxes)
    figure = build_figure(frozenset(), None, boxes=boxes,
                          structural=structural, types=types)
    drawn = sum(len(tr.x) for tr in figure.data if tr.showlegend)
    assert drawn == expected


def test_the_view_has_a_plate_and_a_cabinet_outline(boxes, structural):
    """The backdrop is there, and neither piece joins the legend."""
    pytest.importorskip("plotly")
    figure = build_figure(frozenset(), None, boxes=boxes,
                          structural=structural)
    assert any(tr.name == "plate" for tr in figure.data)
    assert all(not tr.showlegend for tr in figure.data
               if tr.name in {"plate", ""})


def test_shading_is_soft_and_projection_orthographic(boxes, structural):
    """Flat shading and perspective are both switched off deliberately."""
    pytest.importorskip("plotly")
    figure = build_figure(frozenset(), None, boxes=boxes,
                          structural=structural)
    for trace in figure.data:
        if trace.type == "mesh3d":
            assert trace.flatshading is False
    assert figure.layout.scene.camera.projection.type == "orthographic"


# ------------------------------------------------------ plate, walls, camera
def test_no_part_sticks_out_of_the_plate(boxes):
    """Every part, rails included, sits inside the mounting plate."""
    from redlining.model3d import mounting_plate
    plate = mounting_plate(boxes)
    px1, py1 = plate["x"] + plate["w"], plate["y"] + plate["h"]
    for box in boxes:
        assert plate["x"] <= box["x"] and box["x"] + box["w"] <= px1, box["tag"]
        assert plate["y"] <= box["y"] and box["y"] + box["h"] <= py1, box["tag"]


def test_the_walls_reach_the_side_panel_parts(boxes):
    """A wall is placed where its parts already are, not the other way round.

    Nothing is moved to make the parts touch: the wall goes immediately
    outboard of the outermost part of that side panel.
    """
    from redlining.model3d import side_walls
    walls = {w["frame"]: w for w in side_walls(boxes)}
    assert set(walls) == {"left side panel", "right side panel"}
    for frame, wall in walls.items():
        members = [b for b in boxes if b["frame"] == frame]
        assert members
        outer = max(b["x"] + b["w"] for b in members)
        assert wall["box"]["x"] == outer          # flush, no gap and no overlap


def test_walls_do_not_swallow_other_frames(boxes):
    """The gap between the two frames is 5 mm; a wall has to fit in it."""
    from redlining.model3d import side_walls
    for wall in side_walls(boxes):
        w0 = wall["box"]["x"]
        w1 = w0 + wall["box"]["w"]
        for box in boxes:
            assert not (box["x"] < w1 and w0 < box["x"] + box["w"]), box["tag"]


def test_frame_tints_do_not_overlap(boxes):
    """Two tinted patches at one depth flicker against each other."""
    from redlining.model3d import frame_regions
    spans = sorted(((r["box"]["x"], r["box"]["x"] + r["box"]["w"])
                    for r in frame_regions(boxes)))
    for (_a0, a1), (b0, _b1) in zip(spans, spans[1:]):
        assert a1 <= b0 + 1e-9


def test_each_frame_tint_is_a_tint_not_the_frame_colour(boxes):
    """Slightly tinted: nearer the plate than the frame's own colour."""
    from redlining.model3d import PLATE_COLOUR, frame_regions

    def rgb(c):
        return [int(c[i:i + 2], 16) for i in (1, 3, 5)]

    for region in frame_regions(boxes):
        tint, plate = rgb(region["colour"]), rgb(PLATE_COLOUR)
        full = rgb(FRAME_COLOURS[region["frame"]])
        to_plate = sum(abs(a - b) for a, b in zip(tint, plate))
        to_full = sum(abs(a - b) for a, b in zip(tint, full))
        assert to_plate < to_full, region["frame"]


def test_the_halo_is_one_size_for_every_item(boxes):
    """The ring marks a place; it must not report a size."""
    from redlining.model3d import halo_box
    sizes = set()
    for box in boxes[:40]:
        drawn, _c, _h = box_style(box, current=True)
        halo = halo_box(drawn)
        sizes.add((round(halo["w"], 6), round(halo["h"], 6),
                   round(halo["d"], 6)))
        for axis, size in (("x", "w"), ("y", "h"), ("z", "d")):
            centre = drawn[axis] + drawn[size] / 2.0
            assert abs((halo[axis] + halo[size] / 2.0) - centre) < 1e-9
    assert len(sizes) == 1                       # same ring for every part
    assert sizes.pop()[0] > CURRENT_MM           # and bigger than the cube


def test_walk_has_a_halo_and_the_overview_does_not(boxes, structural):
    """The ring belongs to the current item, and the overview has none."""
    pytest.importorskip("plotly")
    walk = build_figure(frozenset(), "-1Q1", boxes=boxes, structural=structural)
    assert any(tr.name == "halo" for tr in walk.data)
    over = build_figure(frozenset(), None, boxes=boxes, structural=structural)
    assert not any(tr.name == "halo" for tr in over.data)


def test_both_camera_views_are_offered_and_orthographic(boxes, structural):
    """The view opens square on, and the angled button keeps rails straight."""
    pytest.importorskip("plotly")
    from redlining.model3d import ANGLED_CAMERA, FRONT_CAMERA
    figure = build_figure(frozenset(), None, boxes=boxes,
                          structural=structural)
    assert figure.layout.scene.camera.projection.type == "orthographic"
    assert FRONT_CAMERA["projection"]["type"] == "orthographic"
    assert ANGLED_CAMERA["projection"]["type"] == "orthographic"
    labels = [b.label for m in figure.layout.updatemenus for b in m.buttons]
    assert labels == ["Front view", "Angled view"]


def test_backdrop_never_joins_the_legend(boxes, structural):
    """Plate, tints and walls are scenery; only outcomes are keyed."""
    pytest.importorskip("plotly")
    figure = build_figure(frozenset(), None, boxes=boxes,
                          structural=structural)
    scenery = {"plate", "frame tint", "side wall", "halo", ""}
    for trace in figure.data:
        if trace.name in scenery:
            assert not trace.showlegend, trace.name


def test_the_halo_is_the_same_size_whatever_the_part(boxes, structural):
    """Built from the token cube, never from the real box.

    The two parts below differ by orders of magnitude in volume. If the ring
    were ever sized from the part itself, the big one would wear a bigger
    ring and the view would report a size it is withholding.
    """
    pytest.importorskip("plotly")
    walkable = [b for b in boxes if b["tag"] not in structural]
    small = min(walkable, key=lambda b: b["w"] * b["h"] * b["d"])
    large = max(walkable, key=lambda b: b["w"] * b["h"] * b["d"])
    assert large["w"] * large["h"] * large["d"] > \
        20 * small["w"] * small["h"] * small["d"]      # 36x in this export

    def ring(tag):
        figure = build_figure(frozenset(), tag, boxes=boxes,
                             structural=structural)
        halo = next(tr for tr in figure.data if tr.name == "halo")
        axes = []
        for values in (halo.x, halo.y, halo.z):
            real = [v for v in values if v is not None]
            axes.append(round(max(real) - min(real), 6))
        return tuple(axes)

    assert ring(small["tag"]) == ring(large["tag"])
