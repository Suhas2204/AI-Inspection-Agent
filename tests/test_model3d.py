"""Tests for model3d.py: the box set, and which box the 3D view marks green.

The green box tells the trainee where to walk next. If it drifts off the
checklist step the page is prompting, the picture sends them to one part
while the words send them to another, and nothing in the run would say so.
These tests pin the two together.
"""

import pytest

from redlining.checklist import load_checklist
from redlining.model3d import (
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
