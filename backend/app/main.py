"""API for video generation, job tracking, and consent-based reuse."""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from .config import RenderQuality, settings
from .generator import generate_manim_code
from .reuse import enabled as reuse_enabled, suggest, publish
from .sandbox import validate_manim_code
from .schemas import (GenerateRequest, GenerateResponse, JobStatusResponse,
                      SuggestionRequest, SuggestionResponse, VideoSuggestion)
from .store import store
from .video_storage import enabled as r2_enabled, signed_url, upload

executor = ThreadPoolExecutor(max_workers=2)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    for job in store.unfinished():
        executor.submit(_run_job, job["job_id"], GenerateRequest(**job))
    yield
    executor.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="manim-video API", version="0.2.0", lifespan=lifespan)


def _check_auth(x_api_key: str | None) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key.")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest, x_api_key: str | None = Header(default=None)) -> GenerateResponse:
    _check_auth(x_api_key)
    if len(req.prompt) > settings.max_prompt_chars:
        raise HTTPException(status_code=400, detail="Prompt too long.")
    if req.quality == RenderQuality.k and not settings.allow_high_quality:
        raise HTTPException(status_code=400, detail="4k renders are disabled.")
    if req.share_for_reuse and not reuse_enabled():
        raise HTTPException(status_code=503, detail="Video reuse is not configured.")
    try:
        r2_enabled()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    job = store.create(prompt=req.prompt, provider=(req.provider or settings.llm_provider).value,
                       model=req.model or settings.llm_model, quality=req.quality.value,
                       scene_name=req.scene_name, share_for_reuse=req.share_for_reuse,
                       reuse_indexed=False, reuse_error=None, r2_key=None)
    executor.submit(_run_job, job["job_id"], req)
    return GenerateResponse(job_id=job["job_id"])


def _run_job(job_id: str, req: GenerateRequest) -> None:
    store.update(job_id, status="running", error=None)
    try:
        job_dir = Path(settings.jobs_dir) / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        scene = job_dir / "scene.py"
        if scene.exists():
            code = scene.read_text(encoding="utf-8")
            validate_manim_code(code, req.scene_name)
        else:
            code, provider, model = generate_manim_code(req.prompt, req.provider, req.model, req.scene_name)
            validate_manim_code(code, req.scene_name)
            scene.write_text(code, encoding="utf-8")
            store.update(job_id, code=code, provider=provider, model=model)

        request = job_dir / "request.json"
        if not request.exists():
            temporary = job_dir / "request.tmp"
            temporary.write_text(json.dumps({"scene_name": req.scene_name, "quality": req.quality.value}), encoding="utf-8")
            os.replace(temporary, request)

        result_path = job_dir / "result.json"
        deadline = time.monotonic() + settings.render_timeout_sec + 60
        while not result_path.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("Render worker did not finish. Check that the worker container is running.")
            time.sleep(0.5)
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if not result["ok"]:
            raise RuntimeError(result["error"])
        final = job_dir / "output.mp4"
        if not final.exists():
            raise RuntimeError("Render worker reported success without output.mp4.")
        key = upload(job_id, final)
        job = store.update(job_id, status="succeeded", log=result.get("log", ""),
                           r2_key=key, video_url=f"/api/videos/{job_id}.mp4")
        try:
            publish(job)
            if req.share_for_reuse:
                store.update(job_id, reuse_indexed=True)
        except Exception as exc:
            store.update(job_id, reuse_error=f"{type(exc).__name__}: {exc}")
    except Exception as exc:
        store.update(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")


@app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
def job_status(job_id: str, x_api_key: str | None = Header(default=None)) -> JobStatusResponse:
    _check_auth(x_api_key)
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JobStatusResponse(**job)


@app.post("/api/jobs/{job_id}/retry-reuse", response_model=JobStatusResponse)
def retry_reuse(job_id: str, x_api_key: str | None = Header(default=None)) -> JobStatusResponse:
    _check_auth(x_api_key)
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job["status"] != "succeeded" or not job["share_for_reuse"]:
        raise HTTPException(status_code=409, detail="Only completed, shared videos can be indexed for reuse.")
    if not reuse_enabled():
        raise HTTPException(status_code=503, detail="Video reuse is not configured.")
    if job["reuse_indexed"]:
        return JobStatusResponse(**job)
    try:
        publish(job)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        store.update(job_id, reuse_error=error)
        raise HTTPException(status_code=503, detail=f"Reuse indexing failed: {error}") from exc
    updated = store.update(job_id, reuse_indexed=True, reuse_error=None)
    return JobStatusResponse(**updated)


@app.get("/api/videos/{job_id}.mp4")
def get_video(job_id: str, x_api_key: str | None = Header(default=None)):
    _check_auth(x_api_key)
    job = store.get(job_id)
    if not job or job["status"] != "succeeded":
        raise HTTPException(status_code=404, detail="Video not ready.")
    if job.get("r2_key"):
        return RedirectResponse(signed_url(job["r2_key"]))
    path = Path(settings.jobs_dir) / job_id / "output.mp4"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video not found.")
    return FileResponse(path, media_type="video/mp4", filename=f"{job_id}.mp4")


@app.post("/api/suggestions", response_model=SuggestionResponse)
def suggestions(req: SuggestionRequest, x_api_key: str | None = Header(default=None)) -> SuggestionResponse:
    _check_auth(x_api_key)
    if not reuse_enabled():
        raise HTTPException(status_code=503, detail="Video reuse is not configured.")
    if len(req.prompt) > settings.max_prompt_chars:
        raise HTTPException(status_code=400, detail="Prompt too long.")
    matches = []
    try:
        for hit in suggest(req.prompt, req.quality.value):
            job = store.get(hit["payload"]["job_id"])
            if job and job["status"] == "succeeded" and job["share_for_reuse"]:
                matches.append(VideoSuggestion(job_id=job["job_id"], prompt=job["prompt"],
                                               score=hit["score"], video_url=job["video_url"]))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Similarity search unavailable: {exc}") from exc
    return SuggestionResponse(suggestions=matches)
