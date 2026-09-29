"""Render queued scenes in a container with no network or LLM credentials."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from .config import settings
from .sandbox import render_scene, validate_manim_code


def _write_result(job_dir: Path, result: dict) -> None:
    temporary = job_dir / "result.tmp"
    temporary.write_text(json.dumps(result), encoding="utf-8")
    os.replace(temporary, job_dir / "result.json")


def process(job_dir: Path) -> None:
    try:
        request = json.loads((job_dir / "request.json").read_text(encoding="utf-8"))
        code = (job_dir / "scene.py").read_text(encoding="utf-8")
        validate_manim_code(code, request["scene_name"])
        video, log = render_scene(job_dir, request["scene_name"], request["quality"], settings.render_timeout_sec)
        final = job_dir / "output.mp4"
        if video.resolve() != final.resolve():
            shutil.copyfile(video, final)
        _write_result(job_dir, {"ok": True, "log": log[-8000:]})
    except Exception as exc:
        _write_result(job_dir, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def main() -> None:
    root = Path(settings.jobs_dir)
    root.mkdir(parents=True, exist_ok=True)
    while True:
        for request in root.glob("*/request.json"):
            job_dir = request.parent
            if not (job_dir / "result.json").exists():
                process(job_dir)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
