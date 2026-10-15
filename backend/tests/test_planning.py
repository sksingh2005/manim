"""Validate proposed geometry and timing without rendering or an external model."""

import pytest
from pydantic import ValidationError

from app.planning import Rect, Storyboard, parse_storyboard, place_message_labels, prepare_storyboard, validate_storyboard


def test_valid_board(board, lesson):
    validate_storyboard(board, lesson)


def test_small_actions_flow_with_one_hold_at_phase_end(board, lesson):
    first = board.beats[0].model_copy(deep=True)
    next_action = first.model_copy(deep=True)
    next_action.transition = "highlight"
    board.beats.insert(1, next_action)
    first.hold_seconds = 5
    board.beats[0] = first
    repaired = prepare_storyboard(board)
    assert repaired.beats[0].hold_seconds == 0
    assert 1.5 <= repaired.beats[1].hold_seconds <= 3.5
    assert repaired.beats[2].hold_seconds >= 2.5
    validate_storyboard(repaired, lesson)


def test_validator_rejects_idle_pause_inside_phase(board, lesson):
    board.beats.insert(1, board.beats[0].model_copy(deep=True))
    with pytest.raises(ValueError, match="intermediate action must flow"):
        validate_storyboard(board, lesson)


def test_long_model_delays_are_reduced_without_changing_content(board, lesson):
    for beat in board.beats:
        beat.animation_seconds, beat.hold_seconds = 6, 8
    before = board.model_dump()
    repaired = prepare_storyboard(board)
    validate_storyboard(repaired, lesson)
    assert board.model_dump() == before
    assert all(beat.animation_seconds < 2 for beat in repaired.beats)
    assert all(beat.hold_seconds <= 3.5 for beat in repaired.beats)
    assert [beat.caption for beat in repaired.beats] == [beat.caption for beat in board.beats]


@pytest.mark.parametrize("y", [0.29, -0.29, 0.04])
def test_moves_labels_off_title_caption_and_route(board, lesson, y):
    board.beats[0].connectors[0].label_region.y = y
    before = board.model_dump()
    repaired = place_message_labels(board)
    validate_storyboard(repaired, lesson)
    assert board.model_dump() == before
    moved = repaired.beats[0].connectors[0].label_region
    assert moved.width == board.beats[0].connectors[0].label_region.width
    assert moved.height == board.beats[0].connectors[0].label_region.height
    # Only this label's position changes, preserving teaching and timing.
    expected = board.model_copy(deep=True)
    expected.beats[0].connectors[0].label_region = moved
    assert repaired == expected
    assert place_message_labels(repaired) == repaired


def test_preserves_valid_labels(board):
    assert place_message_labels(board) == board


def test_joint_placement_separates_messages_and_avoids_both_routes(board, lesson):
    from app.planning import Point

    beat = board.beats[0]
    other = beat.connectors[0].model_copy(deep=True)
    other.points = [Point(x=-0.12, y=-0.015), Point(x=0.12, y=-0.015)]
    beat.connectors.append(other)
    beat.animation_seconds = 3
    before = board.model_dump()
    with pytest.raises(ValueError, match="message 0 overlaps or crowds message 1"):
        validate_storyboard(board, lesson)
    repaired = place_message_labels(board)
    validate_storyboard(repaired, lesson)
    assert repaired.beats[0].connectors[0].label_region != repaired.beats[0].connectors[1].label_region
    assert board.model_dump() == before


def test_small_shift_fixes_encoder_label_clearance(board, lesson):
    beat = board.beats[0]
    beat.objects[0].region = Rect(x=-0.05, y=-0.08, width=0.14, height=0.12)
    beat.objects[1].region = Rect(x=0.22, y=0.14, width=0.16, height=0.08)
    beat.connectors[0].label_region = Rect(x=0.085, y=-0.02, width=0.10, height=0.06)
    with pytest.raises(ValueError, match="overlaps or crowds message"):
        validate_storyboard(board, lesson)
    repaired = place_message_labels(board)
    validate_storyboard(repaired, lesson)
    moved = repaired.beats[0].connectors[0].label_region
    assert moved.width == 0.10 and moved.height == 0.06
    assert abs(moved.x - 0.085) < 0.01
    assert abs(moved.y + 0.02) < 0.01


def test_completed_phase_can_exceed_preferred_pause_when_total_fits(board, lesson):
    board.beats[0].animation_seconds = 0.5
    board.beats[0].caption = " ".join(["word"] * 30)
    before = board.model_dump()
    repaired = prepare_storyboard(board)
    assert board.model_dump() == before
    assert repaired.beats[0].hold_seconds > 3.5
    validate_storyboard(repaired, lesson)


def test_excessive_text_still_requires_repair_when_total_cannot_fit(board, lesson):
    # Short words keep captions within their schema limit while exceeding the
    # reading budget. No normalization may silently skip their reading time.
    board.beats[0].caption = " ".join(["a"] * 65)
    board.beats[1].caption = " ".join(["b"] * 65)
    lesson.takeaway = board.beats[1].caption
    repaired = prepare_storyboard(board)
    with pytest.raises(ValueError, match="reading hold needs"):
        validate_storyboard(repaired, lesson)


def test_pacing_preserves_content_and_bounds_idle_holds(board, lesson):
    board.beats[0].animation_seconds = 0.5
    before = board.model_dump()
    repaired = prepare_storyboard(board)
    validate_storyboard(repaired, lesson)
    assert board.model_dump() == before
    expected = board.model_copy(deep=True)
    expected.beats[0].animation_seconds = 1.45
    assert repaired == expected


def test_repairs_route_crossing_middle_box(board, lesson):
    from app.planning import VisualObject

    beat = board.beats[0]
    beat.hold_seconds = 6
    beat.objects.append(VisualObject(id="middle", kind="box", text="C", font_size=28,
        color="white", region=Rect(x=0, y=0.04, width=0.08, height=0.08)))
    before = board.model_dump()
    repaired = prepare_storyboard(board)
    validate_storyboard(repaired, lesson)
    assert board.model_dump() == before
    connector = repaired.beats[0].connectors[0]
    assert connector.points != beat.connectors[0].points
    original = beat.connectors[0]
    assert (connector.source, connector.target, connector.label) == (
        original.source, original.target, original.label)
    assert repaired.beats[0].objects == beat.objects


def test_repairs_arrow_endpoints_inside_boxes(board, lesson):
    from app.planning import Point

    board.beats[0].connectors[0].points = [Point(x=-0.22, y=0.04), Point(x=0.22, y=0.04)]
    repaired = prepare_storyboard(board)
    validate_storyboard(repaired, lesson)


def test_places_label_beside_vertical_route(board, lesson):
    from app.planning import Point

    beat = board.beats[0]
    beat.objects[0].region = Rect(x=0, y=-0.12, width=0.16, height=0.08)
    beat.objects[1].region = Rect(x=0, y=0.12, width=0.16, height=0.08)
    beat.connectors[0].points = [Point(x=0, y=-0.055), Point(x=0, y=0.055)]
    beat.connectors[0].label_region.y = 0.29
    repaired = place_message_labels(board)
    validate_storyboard(repaired, lesson)
    assert abs(repaired.beats[0].connectors[0].label_region.x) > 0.08


def test_no_space_still_fails_validation(board, lesson):
    board.beats[0].connectors[0].label_region = Rect(x=0, y=0, width=0.70, height=0.60)
    repaired = place_message_labels(board)
    assert repaired == board
    with pytest.raises(ValueError, match="overlaps or crowds"):
        validate_storyboard(repaired, lesson)


def test_label_repair_does_not_bypass_box_collision(board, lesson):
    board.beats[0].objects[1].region = board.beats[0].objects[0].region.model_copy()
    with pytest.raises(ValueError, match="overlaps or crowds"):
        validate_storyboard(place_message_labels(board), lesson)


@pytest.mark.parametrize("x,y", [(0.37, 0), (-0.37, 0), (0, 0.37), (0, -0.37)])
def test_padding_on_every_edge(x, y):
    with pytest.raises(ValidationError, match="12% safe margins"):
        Rect(x=x, y=y, width=0.1, height=0.1)


@pytest.mark.parametrize("region_key,axis,coordinate", [
    ("title_region", "y", 0.35), ("caption_region", "y", -0.35),
    ("title_region", "x", 0.1), ("title_region", "x", -0.1),
])
def test_parse_clamps_regions_inside_every_margin(board, lesson, region_key, axis, coordinate):
    import json

    value = board.model_dump()
    value[region_key][axis] = coordinate
    result = parse_storyboard(json.dumps(value))
    validate_storyboard(result, lesson)
    assert min(result.title_region.bounds) >= -0.38
    assert max(result.title_region.bounds) <= 0.38
    assert min(result.caption_region.bounds) >= -0.38


@pytest.mark.parametrize("size", [0.8, -0.1, "wide"])
def test_parse_cannot_fix_invalid_region_sizes(board, size):
    import json

    value = board.model_dump()
    value["title_region"]["width"] = size
    with pytest.raises(ValidationError):
        parse_storyboard(json.dumps(value))


@pytest.mark.parametrize("change,error", [
    ("crowded_objects", "overlaps or crowds"),
    ("arrow_through_box", "connector crosses or crowds middle"),
    ("arrow_through_message", "connector crosses or crowds message"),
    ("unknown_target", "unknown object"),
    ("short_reading", "reading hold"),
    ("missing_step", "cover every lesson step"),
    ("wrong_takeaway", "lesson takeaway"),
    ("too_long", "outside 5-25"),
    ("crossing_arrows", "connector routes cross"),
    ("floating_arrow", "endpoint must be near"),
])
def test_rejects_invalid_design(board, lesson, change, error):
    value = board.model_dump()
    beat = value["beats"][0]
    if change == "crowded_objects":
        beat["objects"][1]["region"] = beat["objects"][0]["region"]
    elif change == "arrow_through_box":
        beat["hold_seconds"] = 6
        beat["objects"].append({"id": "middle", "kind": "box", "text": "C", "font_size": 28,
                                "color": "white", "region": {"x": 0, "y": 0.04, "width": 0.08, "height": 0.08}})
    elif change == "arrow_through_message":
        beat["connectors"][0]["label_region"]["y"] = 0.04
    elif change == "unknown_target":
        beat["connectors"][0]["target"] = "missing"
    elif change == "short_reading":
        beat["hold_seconds"] = 1.5
    elif change == "missing_step":
        value["beats"][1]["lesson_step"] = 0
    elif change == "wrong_takeaway":
        value["beats"][1]["caption"] = "Different conclusion"
    elif change == "too_long":
        for item in value["beats"]:
            item["hold_seconds"], item["animation_seconds"] = 12, 2
    elif change == "crossing_arrows":
        beat["animation_seconds"], beat["hold_seconds"] = 4, 6
        other = dict(beat["connectors"][0])
        other["label_region"] = {"x": 0, "y": -0.1, "width": 0.16, "height": 0.07}
        beat["connectors"].append(other)
    elif change == "floating_arrow":
        beat["connectors"][0]["points"][0]["x"] = -0.05
    with pytest.raises(ValueError, match=error):
        validate_storyboard(Storyboard.model_validate(value), lesson)


def test_checks_entire_bent_route(board, lesson):
    value = board.model_dump()
    # Endpoints remain free, but a detour passes through the title region.
    value["beats"][0]["connectors"][0]["points"] = [
        {"x": -0.12, "y": 0.04}, {"x": -0.12, "y": 0.32},
        {"x": 0.12, "y": 0.32}, {"x": 0.12, "y": 0.04},
    ]
    with pytest.raises(ValueError, match="connector crosses or crowds title"):
        validate_storyboard(Storyboard.model_validate(value), lesson)


def test_rejects_nonfinite_coordinates():
    with pytest.raises(ValidationError):
        Rect(x=float("nan"), y=0, width=0.1, height=0.1)


def test_rejects_fast_arrow_reveal(board, lesson):
    board.beats[0].animation_seconds = 0.5
    with pytest.raises(ValueError, match="animation needs at least 1.45s"):
        validate_storyboard(board, lesson)


def test_fade_budget_includes_removal_reveal_and_arrow(board, lesson):
    board.beats[0].transition = "fade"
    board.beats[0].animation_seconds = 1.0
    with pytest.raises(ValueError, match="animation needs at least 1.85s"):
        validate_storyboard(board, lesson)
    board.beats[0].animation_seconds = 1.85
    validate_storyboard(board, lesson)


def test_final_frame_needs_longer_hold(board, lesson):
    board.beats[-1].hold_seconds = 1.5
    with pytest.raises(ValueError, match="reading hold needs at least 2.50s"):
        validate_storyboard(board, lesson)
