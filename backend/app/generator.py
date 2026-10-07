"""Natural language -> Manim CE code via LangChain (multi-provider)."""

from __future__ import annotations

import os
import re
import time
import logging
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from .config import LLMProvider, settings
from .planning import LessonPlan, Storyboard, validate_storyboard

SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "manim_system.txt"


def load_system_prompt(scene_name: str) -> str:
    """Read the shared teaching and scene-design contract for every generation."""
    template = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    if not template.strip() or "{scene_name}" not in template:
        raise ValueError("Manim system prompt must be nonempty and contain {scene_name}.")
    # Replace only our token; Python examples and formulas can contain literal braces.
    return template.replace("{scene_name}", scene_name)

CODE_FENCE_RE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
logger = logging.getLogger(__name__)


def _is_google_rate_limit(error: Exception) -> bool:
    """Recognize Gemini quota errors, including errors wrapped by LangChain."""
    current: BaseException | None = error
    while current is not None:
        if type(current).__name__ == "ResourceExhausted":
            return True
        message = str(current).lower()
        if "429" in message and ("quota" in message or "rate limit" in message):
            return True
        current = current.__cause__ or current.__context__
    return False


def _is_google_daily_quota(error: Exception) -> bool:
    """A daily quota cannot be cleared by the short rate-limit retry."""
    current: BaseException | None = error
    while current is not None:
        message = str(current).lower()
        if "perday" in message or "requests per day" in message or "daily quota" in message:
            return True
        current = current.__cause__ or current.__context__
    return False


def get_chat_model(provider: LLMProvider | None = None, model: str | None = None) -> BaseChatModel:
    """LangChain chat model factory. Supports OpenAI / Anthropic / Gemini."""
    prov = provider or settings.llm_provider
    model_name = model or settings.llm_model

    if prov == LLMProvider.openai:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout,
            api_key=settings.openai_api_key or os.environ.get("OPENAI_API_KEY"),
        )
    if prov == LLMProvider.anthropic:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model_name,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout,
            api_key=settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"),
        )
    if prov == LLMProvider.google:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout,
            api_key=settings.google_api_key
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GEMINI_API_KEY"),
        )
    raise ValueError(f"Unknown provider: {prov}")


def extract_code(raw: str) -> str:
    """Strip markdown fences if the model added them anyway."""
    m = CODE_FENCE_RE.search(raw)
    if m:
        return m.group(1).strip()
    return raw.strip()


def generate_manim_code(
    prompt: str,
    provider: LLMProvider | None = None,
    model: str | None = None,
    scene_name: str = "GeneratedScene",
    *,
    lesson_plan: LessonPlan | None = None,
    storyboard: Storyboard | None = None,
) -> tuple[str, str, str]:
    """Returns (code, resolved_provider, resolved_model). Raises on LLM error."""
    if (lesson_plan is None) != (storyboard is None):
        raise ValueError("Code generation requires both the lesson plan and storyboard, or neither")
    system = load_system_prompt(scene_name)
    llm = get_chat_model(provider, model)
    user = f"Create a Manim scene for this request:\n{prompt.strip()}"
    if lesson_plan is not None and storyboard is not None:
        validate_storyboard(storyboard, lesson_plan)
        user += (
            "\n\nImplement this validated lesson and storyboard. Do not invent a different lesson."
            "\nUse exact text and beat order. Coordinates and dimensions are fractions of the full"
            " frame, centered at ORIGIN: multiply x/width by config.frame_width and y/height by"
            " config.frame_height. Each beat is a complete visible-state snapshot. Allocate the"
            " title and caption to their reserved regions. Connector points specify complete"
            " routes; draw segments and an arrowhead on the final segment. Respect the total"
            " animation_seconds for all plays in each beat and hold_seconds after them."
            "\nFit actual rendered text in its region without shrinking below minimum font size."
            " Clear old connectors and labels before transitions; use fades rather than moving"
            " through occupied areas. Recheck measured bounds. Code only."
            f"\nLesson plan:\n{lesson_plan.model_dump_json()}"
            f"\nStoryboard:\n{storyboard.model_dump_json()}"
        )
    messages = [SystemMessage(content=system), HumanMessage(content=user)]
    resolved_provider = provider or settings.llm_provider
    text = _invoke_text(llm, messages, resolved_provider)
    return extract_code(text), resolved_provider.value, model or settings.llm_model


def _invoke_text(llm: BaseChatModel, messages: list, resolved_provider: LLMProvider) -> str:
    """Apply the existing quota policy to every stage and normalize text blocks."""
    for attempt in range(settings.llm_rate_limit_retries + 1):
        try:
            resp = llm.invoke(messages)
            break
        except Exception as exc:
            if (resolved_provider != LLMProvider.google or _is_google_daily_quota(exc)
                    or not _is_google_rate_limit(exc) or attempt == settings.llm_rate_limit_retries):
                raise
            logger.warning("Gemini quota reached; retrying generation in %s seconds (%s/%s)",
                           settings.llm_rate_limit_wait_sec, attempt + 1, settings.llm_rate_limit_retries)
            time.sleep(settings.llm_rate_limit_wait_sec)
    if isinstance(resp.content, str):
        return resp.content
    parts = [block if isinstance(block, str) else block.get("text", "")
             for block in resp.content
             if isinstance(block, str) or isinstance(block, dict) and block.get("type") == "text"]
    if not parts:
        raise ValueError("Model returned no text content")
    return "\n".join(parts)


def _structured_stage(llm, provider, system, user, schema, check=None):
    """Parse a planning stage and allow a bounded repair of invalid proposals."""
    messages = [SystemMessage(content=system), HumanMessage(content=(
        user + "\nReturn a JSON object matching this schema, without Markdown:\n"
        + json.dumps(schema.model_json_schema())
    ))]
    for attempt in range(settings.planning_repair_attempts + 1):
        raw = _invoke_text(llm, messages, provider)
        try:
            # JSON fences are tolerated, but explanations or missing fields are not.
            candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)
            result = schema.model_validate_json(candidate)
            if check is not None:
                check(result)
            return result
        except ValueError as exc:
            if attempt == settings.planning_repair_attempts:
                raise ValueError(f"{schema.__name__} failed validation: {exc}") from exc
            messages.append(HumanMessage(content=(
                f"Your previous proposal failed validation:\n{str(exc)[:6000]}"
                f"\nPrevious proposal:\n{raw[:20000]}"
                "\nReturn a complete corrected JSON object. Preserve the lesson and simplify"
                " the layout or wording if needed. Do not extend the duration or reduce padding."
            )))
    raise RuntimeError("Planning attempts exhausted")


@dataclass
class PlannedScene:
    code: str
    provider: str
    model: str
    lesson_plan: LessonPlan
    storyboard: Storyboard


def generate_planned_scene(
    prompt: str,
    provider: LLMProvider | None = None,
    model: str | None = None,
    scene_name: str = "GeneratedScene",
    *,
    lesson_plan: LessonPlan | None = None,
    storyboard: Storyboard | None = None,
    on_stage: Callable[[str, dict], None] | None = None,
) -> PlannedScene:
    """Plan -> storyboard -> code, with resumable, inspectable planning outputs."""
    if storyboard is not None and lesson_plan is None:
        raise ValueError("A saved storyboard requires its lesson plan")
    # Fail on missing prompts before calling an external model.
    lesson_system = (SYSTEM_PROMPT_PATH.parent / "lesson_plan_system.txt").read_text(encoding="utf-8")
    storyboard_system = (SYSTEM_PROMPT_PATH.parent / "storyboard_system.txt").read_text(encoding="utf-8")
    design_system = load_system_prompt(scene_name)
    llm = get_chat_model(provider, model)
    resolved_provider = provider or settings.llm_provider
    if lesson_plan is None:
        lesson_plan = _structured_stage(llm, resolved_provider, lesson_system,
                                       f"User request:\n{prompt.strip()}", LessonPlan)
    if on_stage:
        on_stage("lesson_plan", lesson_plan.model_dump())
    if storyboard is None:
        # Share the same layout and timing rules without the Python-only output contract.
        design_rules = design_system[
            design_system.index("LAYOUT AND TEXT CONTRACT"):
            design_system.index("FINAL SELF-CHECK BEFORE RETURNING CODE")
        ]
        storyboard = _structured_stage(
            llm, resolved_provider, storyboard_system + "\n" + design_rules,
            f"User request:\n{prompt.strip()}\nLesson plan:\n{lesson_plan.model_dump_json()}",
            Storyboard, lambda board: validate_storyboard(board, lesson_plan),
        )
    else:
        validate_storyboard(storyboard, lesson_plan)
    if on_stage:
        on_stage("storyboard", storyboard.model_dump())
    code, resolved, model_name = generate_manim_code(
        prompt, provider, model, scene_name, lesson_plan=lesson_plan, storyboard=storyboard,
    )
    return PlannedScene(code, resolved, model_name, lesson_plan, storyboard)
