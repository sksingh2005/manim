"""Inspectable lesson and storyboard contracts, without a Manim dependency."""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class LessonStep(PlanModel):
    explanation: str = Field(min_length=1, max_length=600)
    visual_intent: str = Field(min_length=1, max_length=300)


Claim = Annotated[str, Field(min_length=1, max_length=500)]


class LessonPlan(PlanModel):
    audience: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=300)
    scope: str = Field(min_length=1, max_length=300)
    assumptions: list[Claim] = Field(max_length=8)
    key_facts: list[Claim] = Field(min_length=1, max_length=8)
    example: str = Field(min_length=1, max_length=500)
    steps: list[LessonStep] = Field(min_length=2, max_length=5)
    misconceptions: list[Claim] = Field(max_length=5)
    limitations: list[Claim] = Field(max_length=5)
    takeaway: str = Field(min_length=1, max_length=150)


class Rect(PlanModel):
    """Coordinates are fractions of the full frame, with the origin at its center."""

    x: float = Field(ge=-0.5, le=0.5)
    y: float = Field(ge=-0.5, le=0.5)
    width: float = Field(gt=0, le=0.76)
    height: float = Field(gt=0, le=0.76)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (self.x - self.width / 2, self.y - self.height / 2,
                self.x + self.width / 2, self.y + self.height / 2)

    @model_validator(mode="after")
    def within_safe_area(self):
        left, bottom, right, top = self.bounds
        if min(left, bottom) < -0.38 - 1e-9 or max(right, top) > 0.38 + 1e-9:
            raise ValueError("Region extends outside the centered 12% safe margins")
        return self


class VisualObject(PlanModel):
    id: str = Field(min_length=1, max_length=40, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    kind: Literal["box", "circle", "text", "formula"]
    text: str = Field(min_length=1, max_length=150)
    region: Rect
    font_size: int = Field(ge=24, le=48)
    color: Literal["white", "blue", "green", "yellow", "red", "purple"]


class Point(PlanModel):
    x: float = Field(ge=-0.38, le=0.38)
    y: float = Field(ge=-0.38, le=0.38)


class Connector(PlanModel):
    source: str
    target: str
    points: list[Point] = Field(min_length=2, max_length=6)
    label: str = Field(min_length=1, max_length=80)
    label_region: Rect


class Beat(PlanModel):
    lesson_step: int = Field(ge=0, le=4)
    caption: str = Field(min_length=1, max_length=150)
    objects: list[VisualObject] = Field(min_length=1, max_length=6)
    connectors: list[Connector] = Field(max_length=5)
    transition: Literal["reveal", "fade", "highlight"]
    animation_seconds: float = Field(ge=0.4, le=2)
    hold_seconds: float = Field(ge=1.5, le=12)


class Storyboard(PlanModel):
    title: str = Field(min_length=1, max_length=80)
    title_region: Rect
    caption_region: Rect
    beats: list[Beat] = Field(min_length=2, max_length=6)


# Convert normalized coordinates to default Manim scene units for clearance.
FRAME_W, FRAME_H = 128 / 9, 8.0


def _bounds(region: Rect, padding: float = 0) -> tuple[float, float, float, float]:
    left, bottom, right, top = region.bounds
    return (left * FRAME_W - padding, bottom * FRAME_H - padding,
            right * FRAME_W + padding, top * FRAME_H + padding)


def _overlap(a: Rect, b: Rect, clearance: float = 0.25) -> bool:
    al, ab, ar, at = _bounds(a, clearance / 2)
    bl, bb, br, bt = _bounds(b, clearance / 2)
    return al < br and bl < ar and ab < bt and bb < at


def _segment_hits(a: Point, b: Point, rect: Rect, padding: float = 0.15) -> bool:
    """Slab test for an entire line segment against a padded obstacle rectangle."""
    left, bottom, right, top = _bounds(rect, padding)
    low, high = 0.0, 1.0
    for start, end, minimum, maximum in (
        (a.x * FRAME_W, b.x * FRAME_W, left, right),
        (a.y * FRAME_H, b.y * FRAME_H, bottom, top),
    ):
        delta = end - start
        if abs(delta) < 1e-9:
            if not minimum <= start <= maximum:
                return False
        else:
            t1, t2 = (minimum - start) / delta, (maximum - start) / delta
            low, high = max(low, min(t1, t2)), min(high, max(t1, t2))
            if low > high:
                return False
    return True


def _segments_cross(a: Point, b: Point, c: Point, d: Point) -> bool:
    def side(p, q, r):
        return (q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x)

    if (max(a.x, b.x) < min(c.x, d.x) - 1e-9 or
            max(c.x, d.x) < min(a.x, b.x) - 1e-9 or
            max(a.y, b.y) < min(c.y, d.y) - 1e-9 or
            max(c.y, d.y) < min(a.y, b.y) - 1e-9):
        return False
    return side(a, b, c) * side(a, b, d) <= 1e-12 and side(c, d, a) * side(c, d, b) <= 1e-12


def validate_storyboard(board: Storyboard, lesson: LessonPlan) -> None:
    """Validate proposed geometry and timing, not rendered text or factual claims."""
    if _overlap(board.title_region, board.caption_region):
        raise ValueError("Title and caption regions overlap")
    indices = [beat.lesson_step for beat in board.beats]
    if indices != sorted(indices) or set(indices) != set(range(len(lesson.steps))):
        raise ValueError("Beats must cover every lesson step in order using zero-based indices")
    if board.beats[-1].caption != lesson.takeaway:
        raise ValueError("Final caption must be the lesson takeaway")
    total = sum(beat.animation_seconds + beat.hold_seconds for beat in board.beats)
    if not 5 <= total <= 25:
        raise ValueError(f"Storyboard duration {total:.2f}s is outside 5-25 seconds")
    previous_words: set[tuple[str, str]] = set()
    previous_caption = ""
    for index, beat in enumerate(board.beats):
        objects = {obj.id: obj for obj in beat.objects}
        if len(objects) != len(beat.objects):
            raise ValueError(f"Beat {index}: object IDs must be unique")
        regions = [("title", board.title_region), ("caption", board.caption_region)]
        regions += [(obj.id, obj.region) for obj in beat.objects]
        regions += [(f"message {i}", c.label_region) for i, c in enumerate(beat.connectors)]
        for i, (name, region) in enumerate(regions):
            for other_name, other in regions[i + 1:]:
                if _overlap(region, other):
                    raise ValueError(f"Beat {index}: {name} overlaps or crowds {other_name}")
        words = len(beat.caption.split()) if beat.caption != previous_caption else 0
        if index == 0:
            words += len(board.title.split())
        current_words = {(obj.id, obj.text) for obj in beat.objects}
        words += sum(len(text.split()) for _, text in current_words - previous_words)
        words += sum(len(c.label.split()) for c in beat.connectors)
        minimum_hold = max(1.5, words / 3, 2.5 if index == len(board.beats) - 1 else 0)
        if beat.hold_seconds + 1e-9 < minimum_hold:
            raise ValueError(f"Beat {index}: reading hold needs at least {minimum_hold:.2f}s")
        previous_words, previous_caption = current_words, beat.caption
        for i, connector in enumerate(beat.connectors):
            for other in beat.connectors[i + 1:]:
                for a, b in zip(connector.points, connector.points[1:]):
                    for c, d in zip(other.points, other.points[1:]):
                        if _segments_cross(a, b, c, d):
                            raise ValueError(f"Beat {index}: connector routes cross; use separate beats or lanes")
        for connector in beat.connectors:
            if connector.source not in objects or connector.target not in objects:
                raise ValueError(f"Beat {index}: connector references an unknown object")
            if connector.source == connector.target:
                raise ValueError(f"Beat {index}: self-connectors are not supported")
            for a, b in zip(connector.points, connector.points[1:]):
                if math.hypot((b.x - a.x) * FRAME_W, (b.y - a.y) * FRAME_H) < 0.05:
                    raise ValueError(f"Beat {index}: connector segment is too short")
                for name, region in regions:
                    if _segment_hits(a, b, region):
                        raise ValueError(f"Beat {index}: connector crosses or crowds {name}")
            # Prevent labels that name one relationship while the arrow is elsewhere.
            for point, object_id in ((connector.points[0], connector.source),
                                     (connector.points[-1], connector.target)):
                left, bottom, right, top = _bounds(objects[object_id].region)
                x, y = point.x * FRAME_W, point.y * FRAME_H
                distance = math.hypot(max(left - x, 0, x - right), max(bottom - y, 0, y - top))
                if not 0.15 - 1e-9 <= distance <= 0.6:
                    raise ValueError(f"Beat {index}: connector endpoint must be near its box boundary")
