"""Compatibility shim: the 3D view moved to view.model3d.

Re-exports the implementation, which is now in view/. app.py draws the
figure through build_figure, and tests/test_model3d.py exercises most of the
rest -- the box builders, the shape pieces, the layout and the meshes.

`python -m redlining.model3d` still prints the boxes per frame: it hands off
to the view module with runpy.
"""

from __future__ import annotations

from .view.model3d import (  # noqa: F401
    ANGLED_CAMERA,
    BODY_COLOUR,
    CABINET_LINE_COLOUR,
    CABINET_PAD_MM,
    CUBOID_FACES,
    CURRENT_COLOUR,
    CURRENT_HALO_COLOUR,
    CURRENT_HALO_SCALE,
    CURRENT_HOVER,
    CURRENT_MM,
    DATA,
    EDGE_COLOUR,
    FRAME_COLOURS,
    FRAME_NOTE,
    FRAME_TINT,
    FRONT_CAMERA,
    LIGHT_POSITION,
    METAL_COLOUR,
    MIN_SIZE_MM,
    NOT_WALKED,
    NOT_WALKED_COLOUR,
    OVERVIEW_COLOURS,
    PLACEHOLDER_COLOUR,
    PLACEHOLDER_HOVER,
    PLACEHOLDER_MM,
    PLATE_COLOUR,
    PLATE_PAD_MM,
    PLATE_THICKNESS_MM,
    SOFT_LIGHTING,
    STRIP_TAGS,
    STRUCTURAL_COLOUR,
    STRUCTURAL_LABEL,
    UNKNOWN_FRAME_COLOUR,
    WALL_COLOUR,
    WALL_THICKNESS_MM,
    _apply_layout,
    _box_edge_points,
    _cuboid,
    _lines,
    _long_axis,
    _mesh3d,
    _prism,
    _ring,
    blend,
    box_corners,
    box_style,
    build_boxes,
    build_figure,
    cabinet_outline,
    centred_cube,
    clamp_size,
    extents,
    frame_regions,
    halo_box,
    is_shaped,
    legend_label,
    main,
    mesh_arrays,
    mounting_plate,
    outcome_groups,
    part_kind,
    part_types,
    pieces_mesh,
    plain_cube_pieces,
    representative_index,
    shape_pieces,
    side_walls,
    structural_tags,
)

__all__ = [
    "ANGLED_CAMERA", "BODY_COLOUR", "CABINET_LINE_COLOUR", "CABINET_PAD_MM",
    "CUBOID_FACES", "CURRENT_COLOUR", "CURRENT_HALO_COLOUR",
    "CURRENT_HALO_SCALE", "CURRENT_HOVER", "CURRENT_MM", "DATA",
    "EDGE_COLOUR", "FRAME_COLOURS", "FRAME_NOTE", "FRAME_TINT",
    "FRONT_CAMERA", "LIGHT_POSITION", "METAL_COLOUR", "MIN_SIZE_MM",
    "NOT_WALKED", "NOT_WALKED_COLOUR", "OVERVIEW_COLOURS",
    "PLACEHOLDER_COLOUR", "PLACEHOLDER_HOVER", "PLACEHOLDER_MM",
    "PLATE_COLOUR", "PLATE_PAD_MM", "PLATE_THICKNESS_MM", "SOFT_LIGHTING",
    "STRIP_TAGS", "STRUCTURAL_COLOUR", "STRUCTURAL_LABEL",
    "UNKNOWN_FRAME_COLOUR", "WALL_COLOUR", "WALL_THICKNESS_MM", "blend",
    "box_corners", "box_style", "build_boxes", "build_figure",
    "cabinet_outline", "centred_cube", "clamp_size", "extents",
    "frame_regions", "halo_box", "is_shaped", "legend_label", "main",
    "mesh_arrays", "mounting_plate", "outcome_groups", "part_kind",
    "part_types", "pieces_mesh", "plain_cube_pieces",
    "representative_index", "shape_pieces", "side_walls", "structural_tags",
]


if __name__ == "__main__":
    import runpy
    import warnings

    # Expected: the re-export above already imported the view module, and
    # run_module executes it again as __main__ so its block runs.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("redlining.view.model3d", run_name="__main__")
