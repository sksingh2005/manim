"""Inspectable lesson and storyboard contracts, without a Manim dependency."""

from __future__ import annotations

import math
import json
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
    animation_seconds: float = Field(ge=0.4, le=6)
    hold_seconds: float = Field(ge=0, le=12)


class Storyboard(PlanModel):
    title: str = Field(min_length=1, max_length=80)
    title_region: Rect
    caption_region: Rect
    beats: list[Beat] = Field(min_length=2, max_length=6)


# Convert normalized coordinates to default Manim scene units for clearance.
FRAME_W, FRAME_H = 128 / 9, 8.0


def parse_storyboard(raw: str) -> Storyboard:
    """Clamp well-formed region centers to the safe frame before schema checks.

    Oversized regions and malformed values still fail. Shifting a center can
    introduce a collision, so callers must normalize and validate the full board.
    """
    data = json.loads(raw)
    if not isinstance(data, dict):
        return Storyboard.model_validate(data)
    regions = [data.get("title_region"), data.get("caption_region")]
    if isinstance(data.get("beats"), list):
        for beat in data["beats"]:
            if not isinstance(beat, dict):
                continue
            for key, region_key in (("objects", "region"), ("connectors", "label_region")):
                if isinstance(beat.get(key), list):
                    regions.extend(item.get(region_key) for item in beat[key] if isinstance(item, dict))
    for region in regions:
        if not isinstance(region, dict):
            continue
        for axis, dimension in (("x", "width"), ("y", "height")):
            center, size = region.get(axis), region.get(dimension)
            if (type(center) in (int, float) and type(size) in (int, float)
                    and math.isfinite(center) and math.isfinite(size)
                    and -0.5 <= center <= 0.5 and 0 < size <= 0.76):
                limit = 0.38 - size / 2
                region[axis] = max(-limit, min(limit, center))
    return Storyboard.model_validate(data)


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


def place_message_labels(board: Storyboard) -> Storyboard:
    """Find nearby free label positions jointly, without changing their text.

    Search is bounded. Impossible assignments remain invalid for model repair.
    All routes and object regions are obstacles, including each label's route.
    """
    result = board.model_copy(deep=True)
    for beat in result.beats:
        obstacles = [result.title_region, result.caption_region]
        obstacles += [obj.region for obj in beat.objects]
        segments = [(a, b) for c in beat.connectors
                    for a, b in zip(c.points, c.points[1:])]

        def free(region):
            return (not any(_overlap(region, other) for other in obstacles)
                    and not any(_segment_hits(a, b, region) for a, b in segments))

        originals = [c.label_region for c in beat.connectors]
        if (all(free(r) for r in originals) and not any(
                _overlap(a, b) for i, a in enumerate(originals) for b in originals[i + 1:])):
            continue
        options = []
        for connector in beat.connectors:
            original = connector.label_region
            candidates = {}

            def add(x, y):
                if (abs(x) + original.width / 2 > 0.38
                        or abs(y) + original.height / 2 > 0.38):
                    return
                region = Rect(x=x, y=y, width=original.width, height=original.height)
                if free(region):
                    candidates[(x, y)] = region

            add(original.x, original.y)
            for distance in (0.04, 0.1, 0.2, 0.4, 0.6, 0.8):
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                               (1, 1), (1, -1), (-1, 1), (-1, -1)):
                    add(original.x + dx * distance / FRAME_W, original.y + dy * distance / FRAME_H)
            for a, b in zip(connector.points, connector.points[1:]):
                dx, dy = (b.x - a.x) * FRAME_W, (b.y - a.y) * FRAME_H
                length = math.hypot(dx, dy)
                if length < 0.05:
                    continue
                nx, ny = -dy / length, dx / length
                offset = (abs(nx) * original.width * FRAME_W
                          + abs(ny) * original.height * FRAME_H) / 2 + 0.18
                for fraction in (0.5, 0.25, 0.75):
                    for extra in (0.0, 0.2, 0.4, 0.6, 0.8):
                        for sign in (1, -1):
                            add(a.x + (b.x - a.x) * fraction + sign * nx * (offset + extra) / FRAME_W,
                                a.y + (b.y - a.y) * fraction + sign * ny * (offset + extra) / FRAME_H)

            # Include narrow gaps missed by offsets beside a segment. Keep grid
            # candidates near this connector, rather than moving labels anywhere.
            def near_route(x, y):
                for a, b in zip(connector.points, connector.points[1:]):
                    ax, ay = a.x * FRAME_W, a.y * FRAME_H
                    dx, dy = (b.x - a.x) * FRAME_W, (b.y - a.y) * FRAME_H
                    length_sq = dx * dx + dy * dy
                    if length_sq < 0.0025:
                        continue
                    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length_sq))
                    if math.hypot(x - ax - t * dx, y - ay - t * dy) <= 2.0:
                        return True
                return False

            left = (-0.38 + original.width / 2) * FRAME_W
            bottom = (-0.38 + original.height / 2) * FRAME_H
            right, top = -left, -bottom
            for xi in range(max(0, int((right - left) / 0.35)) + 1):
                for yi in range(max(0, int((top - bottom) / 0.25)) + 1):
                    x, y = left + xi * 0.35, bottom + yi * 0.25
                    if near_route(x, y):
                        add(x / FRAME_W, y / FRAME_H)
            options.append(sorted(candidates.values(), key=lambda r: math.hypot(
                (r.x - original.x) * FRAME_W, (r.y - original.y) * FRAME_H))[:48])

        # Other misplaced labels must not block a valid joint assignment.
        order = sorted(range(len(options)), key=lambda i: len(options[i]))
        chosen = {}
        remaining = 5000

        def assign(depth):
            nonlocal remaining
            if depth == len(order):
                return True
            index = order[depth]
            for region in options[index]:
                if remaining <= 0:
                    return False
                remaining -= 1
                if any(_overlap(region, other) for other in chosen.values()):
                    continue
                chosen[index] = region
                if assign(depth + 1):
                    return True
                del chosen[index]
            return False

        if assign(0):
            for index, region in chosen.items():
                beat.connectors[index].label_region = region
    return result


def _minimum_timings(board: Storyboard) -> list[tuple[float, float]]:
    timings = []
    previous_words: set[tuple[str, str]] = set()
    previous_caption = ""
    phase_words = 0
    phase_reading_time = 0.0
    phase_messages: set[tuple[str, str, str]] = set()
    for index, beat in enumerate(board.beats):
        animation = max(0.5, 0.85 * len(beat.connectors))
        if beat.transition == "fade":
            animation = 1.0 + 0.85 * len(beat.connectors)
        elif beat.transition == "reveal":
            animation = 0.6 + 0.85 * len(beat.connectors)
        words = len(beat.caption.split()) if beat.caption != previous_caption else 0
        if index == 0:
            words += len(board.title.split())
        current_words = {(obj.id, obj.text) for obj in beat.objects}
        words += sum(len(text.split()) for _, text in current_words - previous_words)
        messages = {(c.source, c.target, c.label) for c in beat.connectors}
        words += sum(len(label.split()) for _, _, label in messages - phase_messages)
        phase_messages.update(messages)
        phase_words += words
        # Captions/labels appear with the actions; some reading happens during
        # the animation. Clearing the old frame contributes no reading time.
        phase_reading_time += 0.75 * (animation - (1.0 if beat.transition == "fade" else 0.0))
        final = index == len(board.beats) - 1
        phase_end = final or board.beats[index + 1].lesson_step != beat.lesson_step
        hold = 0.0
        if phase_end:
            hold = max(2.5 if final else 1.5, phase_words / 3.5 - phase_reading_time)
            phase_words, phase_reading_time = 0, 0.0
            phase_messages.clear()
        timings.append((animation, hold))
        previous_words, previous_caption = current_words, beat.caption
    return timings


def route_connectors(board: Storyboard) -> Storyboard:
    """Repair obstructed routes using a finite set of ports and orthogonal lanes.

    Routes retain source, target and label. Leave impossible routes unchanged
    for full validation and model repair; never remove a relationship to fit.
    """
    result = board.model_copy(deep=True)
    for beat in result.beats:
        objects = {obj.id: obj for obj in beat.objects}
        regions = [result.title_region, result.caption_region]
        regions += [obj.region for obj in beat.objects]
        regions += [c.label_region for c in beat.connectors]

        def ports(region):
            left, bottom, right, top = _bounds(region)
            values = []
            for fraction in (0.5, 0.25, 0.75):
                x, y = left + (right - left) * fraction, bottom + (top - bottom) * fraction
                values += [(left - 0.2, y), (right + 0.2, y),
                           (x, bottom - 0.2), (x, top + 0.2)]
            return [(x / FRAME_W, y / FRAME_H) for x, y in values
                    if abs(x / FRAME_W) <= 0.38 and abs(y / FRAME_H) <= 0.38]

        def near(point, region):
            left, bottom, right, top = _bounds(region)
            x, y = point.x * FRAME_W, point.y * FRAME_H
            distance = math.hypot(max(left - x, 0, x - right), max(bottom - y, 0, y - top))
            return 0.15 - 1e-9 <= distance <= 0.6

        # Lanes just beyond padded obstacle edges, plus the proposed coordinates.
        xs, ys = {0.0}, {0.0}
        for region in regions:
            left, bottom, right, top = _bounds(region, 0.18)
            xs.update((left / FRAME_W, right / FRAME_W))
            ys.update((bottom / FRAME_H, top / FRAME_H))
        xs = sorted(x for x in xs if abs(x) <= 0.38)
        ys = sorted(y for y in ys if abs(y) <= 0.38)
        for index, connector in enumerate(beat.connectors):
            if (connector.source not in objects or connector.target not in objects
                    or connector.source == connector.target):
                continue
            other_segments = [(a, b) for i, c in enumerate(beat.connectors) if i != index
                              for a, b in zip(c.points, c.points[1:])]

            def clear(points):
                for a, b in zip(points, points[1:]):
                    if math.hypot((b.x - a.x) * FRAME_W, (b.y - a.y) * FRAME_H) < 0.05:
                        return False
                    if any(_segment_hits(a, b, region) for region in regions):
                        return False
                    if any(_segments_cross(a, b, c, d) for c, d in other_segments):
                        return False
                return True

            if (clear(connector.points)
                    and near(connector.points[0], objects[connector.source].region)
                    and near(connector.points[-1], objects[connector.target].region)):
                continue
            best, best_cost = None, float("inf")
            for sx, sy in ports(objects[connector.source].region):
                for tx, ty in ports(objects[connector.target].region):
                    routes = [[(sx, sy), (tx, ty)],
                              [(sx, sy), (sx, ty), (tx, ty)],
                              [(sx, sy), (tx, sy), (tx, ty)]]
                    routes += [[(sx, sy), (x, sy), (x, ty), (tx, ty)] for x in xs]
                    routes += [[(sx, sy), (sx, y), (tx, y), (tx, ty)] for y in ys]
                    for route in routes:
                        compact = []
                        for x, y in route:
                            if not compact or (x, y) != (compact[-1].x, compact[-1].y):
                                compact.append(Point(x=x, y=y))
                        if len(compact) < 2:
                            continue
                        cost = sum(math.hypot((b.x - a.x) * FRAME_W, (b.y - a.y) * FRAME_H)
                                   for a, b in zip(compact, compact[1:])) + 0.25 * (len(compact) - 2)
                        if cost < best_cost and clear(compact):
                            best, best_cost = compact, cost
            if best is not None:
                connector.points = best
    return result


def prepare_storyboard(board: Storyboard) -> Storyboard:
    """Repair routes, label placement and timing floors before full validation."""
    result = place_message_labels(route_connectors(place_message_labels(board)))
    timings = []
    for index, (beat, (animation, hold)) in enumerate(zip(result.beats, _minimum_timings(result))):
        # Bound overlong model allocations as well as raising short ones.
        # Full reading pauses belong at phase boundaries, not each small action.
        animation_seconds = max(animation, min(beat.animation_seconds, animation + 0.35))
        # Short pauses are a target, not a text-density gate. A completed phase
        # may need more reading time; retain the total 25s and per-beat limits.
        hold_seconds = max(hold, min(beat.hold_seconds, hold + 0.5)) if hold else 0.0
        timings.append((animation_seconds, hold_seconds))
    if sum(animation + hold for animation, hold in timings) <= 25 and all(
            animation <= 6 and hold <= 12 for animation, hold in timings):
        for beat, (animation, hold) in zip(result.beats, timings):
            beat.animation_seconds, beat.hold_seconds = animation, hold
    return result


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
    for index, (beat, (minimum_animation, minimum_hold)) in enumerate(
            zip(board.beats, _minimum_timings(board))):
        if minimum_hold == 0 and beat.hold_seconds > 0.35:
            raise ValueError(f"Beat {index}: intermediate action must flow into the next action; "
                             "reserve reading holds for the end of this lesson_step phase")
        if beat.animation_seconds + 1e-9 < minimum_animation:
            raise ValueError(f"Beat {index}: animation needs at least {minimum_animation:.2f}s for its transitions and arrows")
        objects = {obj.id: obj for obj in beat.objects}
        if len(objects) != len(beat.objects):
            raise ValueError(f"Beat {index}: object IDs must be unique")
        regions = [("title", board.title_region), ("caption", board.caption_region)]
        regions += [(obj.id, obj.region) for obj in beat.objects]
        regions += [(f"message {i}", c.label_region) for i, c in enumerate(beat.connectors)]
        for i, (name, region) in enumerate(regions):
            for other_name, other in regions[i + 1:]:
                if _overlap(region, other):
                    raise ValueError(
                        f"Beat {index}: {name} overlaps or crowds {other_name}. "
                        f"Normalized bounds (left, bottom, right, top): {name}={region.bounds}, "
                        f"{other_name}={other.bounds}. Leave 0.25 scene units between regions; "
                        "move the message beside its route within the diagram area or simplify this beat."
                    )
        if beat.hold_seconds + 1e-9 < minimum_hold:
            raise ValueError(f"Beat {index}: reading hold needs at least {minimum_hold:.2f}s")
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
