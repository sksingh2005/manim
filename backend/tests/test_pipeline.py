"""Exercise three-stage generation, repair bounds, and saved-plan resumption."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app import generator
from app.config import LLMProvider


CODE = "from manim import *\nclass GeneratedScene(Scene):\n    def construct(self):\n        self.wait(1)\n"


def model_outputs(monkeypatch, *outputs):
    llm = Mock()
    llm.invoke.side_effect = [SimpleNamespace(content=value) for value in outputs]
    monkeypatch.setattr(generator, "get_chat_model", Mock(return_value=llm))
    monkeypatch.setattr(generator.settings, "planning_repair_attempts", 1)
    return llm


@pytest.mark.parametrize("provider", list(LLMProvider))
def test_lesson_then_storyboard_then_code(monkeypatch, lesson, board, provider):
    llm = model_outputs(monkeypatch, lesson.model_dump_json(), board.model_dump_json(), CODE)
    saved = []
    result = generator.generate_planned_scene("Explain a shared decision", provider, "test",
                                              on_stage=lambda stage, value: saved.append((stage, value)))
    assert result.code == CODE.strip()
    assert result.lesson_plan == lesson
    assert result.storyboard == board
    assert result.provider == provider.value
    assert [stage for stage, _ in saved] == ["lesson_plan", "storyboard"]
    calls = llm.invoke.call_args_list
    assert len(calls) == 3
    assert lesson.model_dump_json() in calls[1].args[0][1].content
    assert "executable Python only" not in calls[1].args[0][0].content
    assert board.model_dump_json() in calls[2].args[0][1].content


def test_invalid_storyboard_repaired_before_code(monkeypatch, lesson, board):
    invalid = board.model_copy(deep=True)
    invalid.beats[1].lesson_step = 0
    llm = model_outputs(monkeypatch, lesson.model_dump_json(), invalid.model_dump_json(),
                        board.model_dump_json(), CODE)
    result = generator.generate_planned_scene("Explain a decision")
    assert result.storyboard == board
    assert llm.invoke.call_count == 4
    assert "cover every lesson step" in llm.invoke.call_args_list[2].args[0][-1].content


def test_fast_model_timing_gets_safe_floors_before_code(monkeypatch, lesson, board):
    invalid = board.model_copy(deep=True)
    invalid.beats[0].animation_seconds = 0.5
    invalid.beats[0].hold_seconds = 1.5
    llm = model_outputs(monkeypatch, lesson.model_dump_json(), invalid.model_dump_json(), CODE)
    result = generator.generate_planned_scene("Explain a decision")
    assert llm.invoke.call_count == 3
    assert result.storyboard.beats[0].animation_seconds == 1.45
    generator.validate_storyboard(result.storyboard, lesson)


def test_readable_phase_above_preferred_hold_reaches_code_without_retry(monkeypatch, lesson, board):
    proposal = board.model_copy(deep=True)
    proposal.beats[0].caption = " ".join(["word"] * 30)
    llm = model_outputs(monkeypatch, lesson.model_dump_json(), proposal.model_dump_json(), CODE)
    result = generator.generate_planned_scene("Explain architecture and an example")
    assert llm.invoke.call_count == 3
    assert result.storyboard.beats[0].hold_seconds > 3.5
    assert sum(b.animation_seconds + b.hold_seconds for b in result.storyboard.beats) <= 25
    generator.validate_storyboard(result.storyboard, lesson)


def test_title_outside_margin_is_shifted_and_fully_checked(monkeypatch, lesson, board):
    import json

    value = board.model_dump()
    value["title_region"]["y"] = 0.35
    llm = model_outputs(monkeypatch, lesson.model_dump_json(), json.dumps(value), CODE)
    result = generator.generate_planned_scene("Explain a decision")
    assert llm.invoke.call_count == 3
    assert result.storyboard.title_region.bounds[-1] <= 0.38
    generator.validate_storyboard(result.storyboard, lesson)


def test_crowded_title_label_corrected_saved_and_sent_to_code(monkeypatch, lesson, board):
    invalid = board.model_copy(deep=True)
    invalid.beats[0].connectors[0].label_region.y = 0.29
    llm = model_outputs(monkeypatch, lesson.model_dump_json(), invalid.model_dump_json(), CODE)
    saved = []
    result = generator.generate_planned_scene("Explain a decision",
        on_stage=lambda stage, value: saved.append((stage, value)))
    assert llm.invoke.call_count == 3
    assert saved[-1] == ("storyboard", result.storyboard.model_dump())
    assert result.storyboard != invalid
    assert result.storyboard.model_dump_json() in llm.invoke.call_args_list[-1].args[0][1].content


def test_unplaceable_label_still_uses_bounded_model_repair(monkeypatch, lesson, board):
    from app.planning import Rect

    invalid = board.model_copy(deep=True)
    invalid.beats[0].connectors[0].label_region = Rect(x=0, y=0, width=0.70, height=0.60)
    llm = model_outputs(monkeypatch, lesson.model_dump_json(), invalid.model_dump_json(),
                        invalid.model_dump_json())
    with pytest.raises(ValueError, match="Storyboard failed validation.*overlaps or crowds"):
        generator.generate_planned_scene("Explain a decision")
    assert llm.invoke.call_count == 3
    assert "Normalized bounds" in llm.invoke.call_args_list[-1].args[0][-1].content


def test_invalid_plan_stops_after_bounded_repair(monkeypatch):
    llm = model_outputs(monkeypatch, "{}", "{}")
    with pytest.raises(ValueError, match="LessonPlan failed validation"):
        generator.generate_planned_scene("Explain a decision")
    assert llm.invoke.call_count == 2


def test_repairs_can_be_disabled(monkeypatch):
    llm = model_outputs(monkeypatch, "{}")
    monkeypatch.setattr(generator.settings, "planning_repair_attempts", 0)
    with pytest.raises(ValueError, match="LessonPlan failed validation"):
        generator.generate_planned_scene("Explain a decision")
    assert llm.invoke.call_count == 1


def test_json_fences_are_tolerated(monkeypatch, lesson, board):
    model_outputs(monkeypatch, f"```json\n{lesson.model_dump_json()}\n```", board.model_dump_json(), CODE)
    assert generator.generate_planned_scene("Explain a decision").lesson_plan == lesson


def test_partial_planning_context_cannot_fall_back_to_direct_code(lesson, monkeypatch):
    factory = Mock()
    monkeypatch.setattr(generator, "get_chat_model", factory)
    with pytest.raises(ValueError, match="requires both"):
        generator.generate_manim_code("Explain a decision", lesson_plan=lesson)
    factory.assert_not_called()


def test_failed_storyboard_keeps_successful_lesson(monkeypatch, lesson):
    llm = model_outputs(monkeypatch, lesson.model_dump_json(), "{}", "{}")
    saved = []
    with pytest.raises(ValueError, match="Storyboard failed validation"):
        generator.generate_planned_scene("Explain a decision", on_stage=lambda stage, value: saved.append(stage))
    assert saved == ["lesson_plan"]
    assert llm.invoke.call_count == 3


def test_resume_skips_saved_planning_calls(monkeypatch, lesson, board):
    llm = model_outputs(monkeypatch, CODE)
    result = generator.generate_planned_scene("Explain a decision", lesson_plan=lesson, storyboard=board)
    assert result.lesson_plan == lesson
    assert llm.invoke.call_count == 1


def test_invalid_saved_storyboard_does_not_generate_code(monkeypatch, lesson, board):
    board.beats[0].hold_seconds = 1.5
    llm = model_outputs(monkeypatch, CODE)
    with pytest.raises(ValueError, match="reading hold"):
        generator.generate_planned_scene("Explain a decision", lesson_plan=lesson, storyboard=board)
    llm.invoke.assert_not_called()


def test_text_content_blocks_are_parsed(monkeypatch, lesson, board):
    llm = model_outputs(monkeypatch, [{"type": "text", "text": lesson.model_dump_json()}],
                        [{"type": "text", "text": board.model_dump_json()}],
                        [{"type": "text", "text": CODE}])
    assert generator.generate_planned_scene("Explain a decision").code == CODE.strip()
    assert llm.invoke.call_count == 3


def test_quota_retries_apply_to_planning_stage(monkeypatch, lesson, board):
    llm = model_outputs(monkeypatch, lesson.model_dump_json(), board.model_dump_json(), CODE)
    llm.invoke.side_effect = [RuntimeError("429 rate limit quota"),
                              SimpleNamespace(content=lesson.model_dump_json()),
                              SimpleNamespace(content=board.model_dump_json()), SimpleNamespace(content=CODE)]
    wait = Mock()
    monkeypatch.setattr(generator.time, "sleep", wait)
    generator.generate_planned_scene("Explain a decision", LLMProvider.google)
    wait.assert_called_once()
    assert llm.invoke.call_count == 4
