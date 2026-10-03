"""Job persistence and reuse decisions without external services."""

import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from app import main
from app.store import JobStore
from app.schemas import GenerateRequest


def test_jobs_survive_store_reopen(tmp_path):
    path = str(tmp_path / "state" / "jobs.sqlite3")
    first = JobStore(path)
    job = first.create(prompt="An animated circle", quality="m", share_for_reuse=False)
    first.update(job["job_id"], status="succeeded", video_url="/api/videos/example.mp4")
    reopened = JobStore(path)
    assert reopened.get(job["job_id"])["status"] == "succeeded"
    assert reopened.unfinished() == []


def test_suggestions_require_opt_in_and_completed_video(tmp_path, monkeypatch):
    jobs = JobStore(str(tmp_path / "jobs.sqlite3"))
    shared = jobs.create(prompt="Show a circle", quality="m", share_for_reuse=True)
    private = jobs.create(prompt="Private circle", quality="m", share_for_reuse=False)
    jobs.update(shared["job_id"], status="succeeded", video_url=f"/api/videos/{shared['job_id']}.mp4")
    jobs.update(private["job_id"], status="succeeded", video_url=f"/api/videos/{private['job_id']}.mp4")
    monkeypatch.setattr(main, "store", jobs)
    monkeypatch.setattr(main, "reuse_enabled", lambda: True)
    monkeypatch.setattr(main, "suggest", lambda prompt, quality: [
        {"score": 0.99, "payload": {"job_id": shared["job_id"]}},
        {"score": 0.98, "payload": {"job_id": private["job_id"]}},
    ])
    client = TestClient(main.app)
    response = client.post("/api/suggestions", json={"prompt": "Animate a circle"})
    assert response.status_code == 200
    assert [item["job_id"] for item in response.json()["suggestions"]] == [shared["job_id"]]


def test_video_route_requires_completed_job(tmp_path, monkeypatch):
    jobs = JobStore(str(tmp_path / "jobs.sqlite3"))
    job = jobs.create(prompt="A triangle", quality="m", share_for_reuse=False)
    monkeypatch.setattr(main, "store", jobs)
    client = TestClient(main.app)
    response = client.get(f"/api/videos/{job['job_id']}.mp4")
    assert response.status_code == 404


def test_completed_worker_result_finishes_job(tmp_path, monkeypatch):
    jobs = JobStore(str(tmp_path / "jobs.sqlite3"))
    job = jobs.create(prompt="Show a circle", provider="openai", model="test", quality="m",
                      scene_name="GeneratedScene", share_for_reuse=False)
    job_dir = tmp_path / "renders" / job["job_id"]
    job_dir.mkdir(parents=True)
    (job_dir / "output.mp4").write_bytes(b"video")
    (job_dir / "result.json").write_text(json.dumps({"ok": True, "log": "rendered"}))
    monkeypatch.setattr(main, "store", jobs)
    monkeypatch.setattr(main.settings, "jobs_dir", str(tmp_path / "renders"))
    monkeypatch.setattr(main, "generate_manim_code", lambda *args: (
        "from manim import *\nclass GeneratedScene(Scene):\n    def construct(self):\n        self.wait(1)\n",
        "openai", "test"))
    monkeypatch.setattr(main, "upload", lambda *args: None)
    monkeypatch.setattr(main, "publish", lambda *args: None)
    main._run_job(job["job_id"], GenerateRequest(prompt="Show a circle", model="test"))
    updated = jobs.get(job["job_id"])
    assert updated["status"] == "succeeded"
    assert updated["video_url"] == f"/api/videos/{job['job_id']}.mp4"


def test_retry_reuse_indexes_completed_video_without_rendering(tmp_path, monkeypatch):
    jobs = JobStore(str(tmp_path / "jobs.sqlite3"))
    job = jobs.create(prompt="Show a circle", provider="google", model="test", quality="l",
                      scene_name="GeneratedScene", share_for_reuse=True,
                      reuse_indexed=False, reuse_error="Earlier embedding error", r2_key=None)
    jobs.update(job["job_id"], status="succeeded", video_url=f"/api/videos/{job['job_id']}.mp4")
    published = []
    monkeypatch.setattr(main, "store", jobs)
    monkeypatch.setattr(main, "reuse_enabled", lambda: True)
    monkeypatch.setattr(main, "publish", lambda current: published.append(current["job_id"]))

    client = TestClient(main.app)
    response = client.post(f"/api/jobs/{job['job_id']}/retry-reuse")

    assert response.status_code == 200
    assert response.json()["reuse_indexed"] is True
    assert response.json()["reuse_error"] is None
    assert published == [job["job_id"]]

    response = client.post(f"/api/jobs/{job['job_id']}/retry-reuse")
    assert response.status_code == 200
    assert published == [job["job_id"]]
