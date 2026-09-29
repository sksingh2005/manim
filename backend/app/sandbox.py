"""Validate generated code and render it inside the isolated worker container."""

from __future__ import annotations

import ast
import os
import signal
import subprocess
import tempfile
from pathlib import Path

BLOCKED_MODULES = {"os", "sys", "subprocess", "socket", "pathlib", "shutil", "requests", "urllib"}
BLOCKED_NAMES = {"open", "eval", "exec", "__import__", "compile", "input", "exit", "quit"}
BLOCKED_ATTRS = {"system", "popen", "call", "run", "getoutput"}


def validate_manim_code(code: str, scene_name: str) -> None:
    """Raise ValueError if code is unsafe or structurally invalid."""
    if len(code) > 20_000:
        raise ValueError("Generated code too long (>20000 chars).")
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"Syntax error in generated code: {e}") from e

    scene_classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    if len(scene_classes) != 1 or scene_classes[0].name != scene_name:
        raise ValueError(f"Code must define exactly one class named {scene_name}.")
    cls = scene_classes[0]
    if len(cls.bases) != 1 or not isinstance(cls.bases[0], ast.Name) or cls.bases[0].id not in {"Scene", "ThreeDScene", "MovingCameraScene"}:
        raise ValueError(f"{scene_name} must inherit from a supported Manim Scene class.")
    if not any(isinstance(n, ast.FunctionDef) and n.name == "construct" for n in cls.body):
        raise ValueError(f"{scene_name} must implement def construct(self).")

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            else:
                if not node.module or node.level:
                    raise ValueError("Relative imports are not allowed.")
                mods = [node.module.split(".")[0]]
            for m in mods:
                if m in BLOCKED_MODULES:
                    raise ValueError(f"Blocked import: {m}")
                if m not in {"manim", "math", "numpy"}:
                    raise ValueError(f"Only manim/math/numpy imports allowed, got: {m}")
        if isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            raise ValueError(f"Blocked builtin usage: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr in BLOCKED_ATTRS:
            raise ValueError(f"Blocked call: .{node.attr}()")


QUALITY_FLAG = {"l": "-ql", "m": "-qm", "h": "-qh", "k": "-qk"}


def render_scene(job_dir: Path, scene_name: str, quality: str, timeout_sec: int) -> tuple[Path, str]:
    """Run `manim render` inside job_dir. Returns (mp4_path, combined_log)."""
    if quality not in QUALITY_FLAG:
        raise ValueError("Invalid render quality.")
    cmd = ["manim", "render", QUALITY_FLAG[quality], "--format=mp4", "scene.py", scene_name]
    with tempfile.TemporaryFile(mode="w+b") as output:
        proc = subprocess.Popen(cmd, cwd=job_dir, stdout=output,
                                stderr=subprocess.STDOUT, start_new_session=True)
        try:
            proc.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired as exc:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            raise TimeoutError(f"Manim render exceeded {timeout_sec} seconds.") from exc
        output.seek(0, os.SEEK_END)
        output.seek(max(0, output.tell() - 8000))
        log = f"$ {' '.join(cmd)}\n{output.read().decode('utf-8', errors='replace')}"
    if proc.returncode != 0:
        raise RuntimeError(f"manim render failed (exit {proc.returncode}).\n{log[-4000:]}")
    mp4s = sorted(job_dir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime)
    if not mp4s:
        raise RuntimeError(f"No mp4 produced.\n{log[-4000:]}")
    return mp4s[-1], log
