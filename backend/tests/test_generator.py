"""Prompt-file loading and model message wiring without live LLM calls."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import generator
from app.config import LLMProvider
from app.sandbox import validate_manim_code


def test_shipped_prompt_loads_outside_backend_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    prompt = generator.load_system_prompt("LessonScene")
    assert "class named LessonScene" in prompt
    assert "{scene_name}" not in prompt


def test_loader_preserves_literal_python_and_formula_braces(tmp_path, monkeypatch):
    prompt_file = tmp_path / "system.txt"
    prompt_file.write_text('Class {scene_name}; values = {"x": 1}; formula x^{2}', encoding="utf-8")
    monkeypatch.setattr(generator, "SYSTEM_PROMPT_PATH", prompt_file)
    assert generator.load_system_prompt("LessonScene") == (
        'Class LessonScene; values = {"x": 1}; formula x^{2}'
    )


@pytest.mark.parametrize("provider", list(LLMProvider))
def test_generation_sends_prompt_file_as_system_message(tmp_path, monkeypatch, provider):
    prompt_file = tmp_path / "system.txt"
    prompt_file.write_text("Teach clearly with class {scene_name}.", encoding="utf-8")
    monkeypatch.setattr(generator, "SYSTEM_PROMPT_PATH", prompt_file)
    code = 'from manim import *\nclass LessonScene(Scene):\n    def construct(self):\n        self.wait(1)'
    llm = Mock()
    llm.invoke.return_value = SimpleNamespace(content=f"```python\n{code}\n```")
    factory = Mock(return_value=llm)
    monkeypatch.setattr(generator, "get_chat_model", factory)

    result = generator.generate_manim_code("  Explain a voting process  ", provider, "test-model", "LessonScene")

    factory.assert_called_once_with(provider, "test-model")
    messages = llm.invoke.call_args.args[0]
    assert len(messages) == 2
    assert isinstance(messages[0], SystemMessage)
    assert messages[0].content == "Teach clearly with class LessonScene."
    assert isinstance(messages[1], HumanMessage)
    assert messages[1].content == "Create a Manim scene for this request:\nExplain a voting process"
    assert result == (code, provider.value, "test-model")
    validate_manim_code(result[0], "LessonScene")


def test_each_generation_reads_current_prompt_file(tmp_path, monkeypatch):
    prompt_file = tmp_path / "system.txt"
    monkeypatch.setattr(generator, "SYSTEM_PROMPT_PATH", prompt_file)
    llm = Mock()
    llm.invoke.return_value = SimpleNamespace(content="python code")
    monkeypatch.setattr(generator, "get_chat_model", Mock(return_value=llm))

    for instruction in ("First revision", "Second revision"):
        prompt_file.write_text(instruction + " {scene_name}", encoding="utf-8")
        generator.generate_manim_code("Show a process", scene_name="LessonScene")
        assert llm.invoke.call_args.args[0][0].content == instruction + " LessonScene"


@pytest.mark.parametrize("content", ["", "   ", "Teach with an unspecified class."])
def test_invalid_template_fails_before_model_creation(tmp_path, monkeypatch, content):
    prompt_file = tmp_path / "system.txt"
    prompt_file.write_text(content, encoding="utf-8")
    monkeypatch.setattr(generator, "SYSTEM_PROMPT_PATH", prompt_file)
    factory = Mock()
    monkeypatch.setattr(generator, "get_chat_model", factory)
    with pytest.raises(ValueError, match="Manim system prompt"):
        generator.generate_manim_code("Show a process")
    factory.assert_not_called()


def test_missing_template_fails_before_model_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(generator, "SYSTEM_PROMPT_PATH", tmp_path / "missing.txt")
    factory = Mock()
    monkeypatch.setattr(generator, "get_chat_model", factory)
    with pytest.raises(FileNotFoundError):
        generator.generate_manim_code("Show a process")
    factory.assert_not_called()
