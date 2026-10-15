"""Check built images with disposable, offline containers. No LLM keys required.

Run from the repository root:
    python backend/tests/docker_smoke.py --api-image manim-video-api:optimized \
        --renderer-image manim-video-renderer:optimized
"""

import argparse
import subprocess


API_CHECK = r'''
import importlib.util
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

assert os.getuid() == 1000
assert importlib.util.find_spec("manim") is None
assert all(shutil.which(name) is None for name in ("gcc", "git", "latex", "ffmpeg"))
assert not Path("/app/.env").exists()
import langchain_openai, langchain_anthropic, langchain_google_genai, boto3
from app.generator import load_system_prompt
assert "GeneratedScene" in load_system_prompt("GeneratedScene")
for name in ("lesson_plan_system.txt", "storyboard_system.txt"):
    assert (Path("/app/app/prompts") / name).read_text().strip()
from app.store import store
job = store.create(prompt="Container check", quality="l", share_for_reuse=False)
assert store.get(job["job_id"])["prompt"] == "Container check"
process = subprocess.Popen(["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"])
try:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("API exited before becoming healthy")
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2) as response:
                assert response.status == 200
                break
        except OSError:
            time.sleep(0.2)
    else:
        raise RuntimeError("API did not become healthy within 30 seconds")
finally:
    process.terminate()
    process.wait(timeout=10)
print("API passed: SDK imports, prompt files, writable SQLite volume, HTTP health, and non-root runtime")
'''


RENDERER_CHECK = r'''
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

assert os.getuid() == 1000
assert all(importlib.util.find_spec(name) is None for name in ("fastapi", "langchain_core", "boto3"))
assert all(shutil.which(name) is None for name in ("gcc", "g++", "pkg-config", "git"))
assert not Path("/app/app/generator.py").exists()
assert not Path("/app/.env").exists()
assert all(not os.environ.get(name) for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"))
from app.config import settings
from app.worker import process
job_dir = Path(settings.jobs_dir) / "smoke"
job_dir.mkdir(parents=True)
code = """from manim import *
class GeneratedScene(Scene):
    def construct(self):
        title = Text("Renderer smoke test", font_size=36).to_edge(UP)
        box = Rectangle(width=4.5, height=1.2, color=BLUE)
        label = Text("Text and arrows work", font_size=28).move_to(box)
        formula = MathTex(r"x^2 + y^2 = z^2").next_to(box, DOWN, buff=0.7)
        arrow = Arrow(box.get_left() + LEFT * 1.2, box.get_left(), buff=0.2)
        self.add(title, box, label, formula)
        self.play(GrowArrow(arrow), run_time=1.5)
        self.wait(1)
"""
(job_dir / "scene.py").write_text(code)
(job_dir / "request.json").write_text(json.dumps({"scene_name": "GeneratedScene", "quality": "l"}))
process(job_dir)
result = json.loads((job_dir / "result.json").read_text())
assert result["ok"], result.get("error")
video = job_dir / "output.mp4"
assert video.stat().st_size > 0
probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height",
                        "-show_entries", "format=duration", "-of", "json", str(video)],
                       check=True, capture_output=True, text=True)
metadata = json.loads(probe.stdout)
assert any(stream.get("codec_name") == "h264" and stream.get("height") == 480
           for stream in metadata["streams"])
assert 2.3 <= float(metadata["format"]["duration"]) <= 2.7
print("Renderer passed: worker output, Text, arrows, MathTex, H.264 video, duration, and non-root runtime")
'''


def check_image(image: str, script: str, *, api: bool) -> None:
    command = [
        "docker", "run", "--rm", "--init", "-i", "--network=none", "--read-only",
        "--cap-drop=ALL", "--security-opt=no-new-privileges:true", "--memory=2g", "--cpus=2",
        "--tmpfs", "/tmp:size=512m,mode=1777", "--volume", "/tmp/manim-jobs",
    ]
    if api:
        command += ["--volume", "/tmp/manim-state"]
    command += ["--entrypoint", "python", image, "-"]
    subprocess.run(command, input=script, text=True, check=True, timeout=180)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-image", default="manim-video-api:latest")
    parser.add_argument("--renderer-image", default="manim-video-renderer:latest")
    args = parser.parse_args()
    check_image(args.api_image, API_CHECK, api=True)
    check_image(args.renderer_image, RENDERER_CHECK, api=False)
