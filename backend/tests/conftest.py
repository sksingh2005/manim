"""Small, readable planning fixtures shared by pipeline and job tests."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.planning import LessonPlan, Storyboard


@pytest.fixture
def lesson():
    return LessonPlan(
        audience="Beginners", objective="Understand a shared decision", scope="A simple voting example",
        assumptions=["Illustrative example"], key_facts=["Votes precede the decision"],
        example="Two actors exchange a vote", misconceptions=[], limitations=[],
        steps=[{"explanation": "Ask for a vote", "visual_intent": "Show the request"},
               {"explanation": "Announce the decision", "visual_intent": "Update the message"}],
        takeaway="One shared decision",
    )


@pytest.fixture
def board(lesson):
    objects = [
        {"id": "left", "kind": "box", "text": "Actor A", "font_size": 28, "color": "blue",
         "region": {"x": -0.22, "y": 0.04, "width": 0.16, "height": 0.14}},
        {"id": "right", "kind": "box", "text": "Actor B", "font_size": 28, "color": "green",
         "region": {"x": 0.22, "y": 0.04, "width": 0.16, "height": 0.14}},
    ]
    connector = {
        "source": "left", "target": "right", "points": [{"x": -0.12, "y": 0.04}, {"x": 0.12, "y": 0.04}],
        "label": "Vote", "label_region": {"x": 0, "y": 0.15, "width": 0.16, "height": 0.07},
    }
    return Storyboard.model_validate({
        "title": "Shared decision",
        "title_region": {"x": 0, "y": 0.32, "width": 0.70, "height": 0.10},
        "caption_region": {"x": 0, "y": -0.31, "width": 0.70, "height": 0.12},
        "beats": [
            {"lesson_step": 0, "caption": "First ask for a vote", "objects": objects,
             "connectors": [connector], "transition": "reveal", "animation_seconds": 0.8, "hold_seconds": 4.5},
            {"lesson_step": 1, "caption": lesson.takeaway, "objects": objects,
             "connectors": [connector], "transition": "highlight", "animation_seconds": 0.8, "hold_seconds": 3},
        ],
    })
