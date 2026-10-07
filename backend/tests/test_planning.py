"""Validate proposed geometry and timing without rendering or an external model."""

import pytest
from pydantic import ValidationError

from app.planning import Rect, Storyboard, validate_storyboard


def test_valid_board(board, lesson):
    validate_storyboard(board, lesson)


@pytest.mark.parametrize("x,y", [(0.37, 0), (-0.37, 0), (0, 0.37), (0, -0.37)])
def test_padding_on_every_edge(x, y):
    with pytest.raises(ValidationError, match="12% safe margins"):
        Rect(x=x, y=y, width=0.1, height=0.1)


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
