"""Natural language -> Manim CE code via LangChain (multi-provider)."""

from __future__ import annotations

import os
import re

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from .config import LLMProvider, settings

SYSTEM_PROMPT = """You are an expert Manim Community Edition (python package `manim`) scene author.
Output ONLY valid Python code, no markdown fences, no explanation.

Hard rules:
1. Use ONLY `from manim import *` plus stdlib `math` / `numpy as np` if needed.
2. Define exactly ONE Scene subclass. Its name is {scene_name}. It must implement `def construct(self):`.
3. Keep it short: 1 scene, 5-25 seconds of animation, no external assets, no file I/O, no network.
4. Never use: os, sys, subprocess, socket, pathlib, shutil, open(), eval, exec, __import__, compile.
5. Prefer Text over Tex (Tex needs LaTeX). Use Tex only for short math formulas.
6. End with a clear final frame (no empty fade-out). Use self.wait() appropriately.
7. Code must run with: `manim render -qm --format=mp4 scene.py {scene_name}`.
"""

CODE_FENCE_RE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


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
) -> tuple[str, str, str]:
    """Returns (code, resolved_provider, resolved_model). Raises on LLM error."""
    llm = get_chat_model(provider, model)
    system = SYSTEM_PROMPT.format(scene_name=scene_name)
    user = f"Create a Manim scene for this request:\n{prompt.strip()}"
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    text = resp.content if isinstance(resp.content, str) else str(resp.content)
    resolved_provider = str((provider or settings.llm_provider).value)
    resolved_model = model or settings.llm_model
    return extract_code(text), resolved_provider, resolved_model
