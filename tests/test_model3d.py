"""Tests for model3d.py: the box set, and which box the 3D view marks green.

The green box tells the trainee where to walk next. If it drifts off the
checklist step the page is prompting, the picture sends them to one part
while the words send them to another, and nothing in the run would say so.
These tests pin the two together.
"""

import pytest

from redlining.checklist import load_checklist
from redlining.model3d import (
    FRAME_NOTE,
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
    names = [trace.name for trace in figure.data]
    groups = outcome_groups(boxes, run_results, structural)
    assert names == [legend_label(g) for g in groups]
    assert figure.layout.showlegend is True


def test_walk_mode_has_no_legend(boxes, structural, items, run_results):
    """Mid-walk there is nothing to key, and a legend would name the parts."""
    pytest.importorskip("plotly")
    figure = build_figure(run_results, items[4].tag, boxes=boxes,
                          structural=structural)
    assert figure.layout.showlegend is False


def test_overview_draws_every_part_at_real_size(boxes, structural):
    """Once the walk is over nothing is withheld."""
    pytest.importorskip("plotly")
    figure = build_figure(frozenset(), None, boxes=boxes,
                          structural=structural)
    drawn = sum(len(trace.x) for trace in figure.data)
    assert drawn == 8 * len(boxes)        # eight corners each, nothing dropped


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
