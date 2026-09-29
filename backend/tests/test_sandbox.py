"""Smoke tests for code validation (no LLM / manim binary needed)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.sandbox import validate_manim_code

GOOD = """
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        self.add(Text("hello"))
        self.wait(1)
"""

BAD_IMPORT = """
import os
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        os.system("rm -rf /")
"""


def test_good_passes():
    validate_manim_code(GOOD, "GeneratedScene")


def test_blocked_import_fails():
    try:
        validate_manim_code(BAD_IMPORT, "GeneratedScene")
    except ValueError:
        return
    raise AssertionError("blocked import was not rejected")


def test_extra_class_fails():
    code = GOOD + "\nclass Unexpected(Scene):\n    pass\n"
    try:
        validate_manim_code(code, "GeneratedScene")
    except ValueError:
        return
    raise AssertionError("extra class was not rejected")


def test_scene_must_inherit_manim_scene():
    code = "class GeneratedScene(object):\n    def construct(self):\n        pass\n"
    try:
        validate_manim_code(code, "GeneratedScene")
    except ValueError:
        return
    raise AssertionError("invalid scene base was not rejected")
