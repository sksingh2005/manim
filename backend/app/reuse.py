"""Opt-in semantic video reuse through Qdrant and Gemini embeddings."""

from __future__ import annotations

import uuid
import os

import httpx

from .config import settings


def enabled() -> bool:
    google_key = settings.google_api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    return bool(settings.qdrant_url and google_key)


def _embed(prompt: str) -> list[float]:
    google_key = settings.google_api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not google_key:
        raise RuntimeError("Set GOOGLE_API_KEY or GEMINI_API_KEY to enable prompt embeddings.")
    response = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/{settings.embedding_model}:embedContent",
        headers={"x-goog-api-key": google_key},
        json={
            "content": {"parts": [{"text": prompt}]},
            "taskType": "SEMANTIC_SIMILARITY",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["embedding"]["values"]


def _collection(vector_size: int) -> str:
    url = f"{settings.qdrant_url.rstrip('/')}/collections/{settings.qdrant_collection}"
    with httpx.Client(timeout=15) as client:
        response = client.get(url)
        if response.status_code == 404:
            response = client.put(url, json={"vectors": {"size": vector_size, "distance": "Cosine"}})
        response.raise_for_status()
    return url


def publish(job: dict) -> None:
    if not enabled() or not job["share_for_reuse"]:
        return
    vector = _embed(job["prompt"])
    url = _collection(len(vector))
    point = {"id": str(uuid.UUID(job["job_id"])), "vector": vector,
             "payload": {"job_id": job["job_id"], "quality": job["quality"]}}
    response = httpx.put(f"{url}/points?wait=true", json={"points": [point]}, timeout=15)
    response.raise_for_status()


def suggest(prompt: str, quality: str) -> list[dict]:
    if not enabled():
        return []
    vector = _embed(prompt)
    url = _collection(len(vector))
    body = {"query": vector, "limit": 5, "with_payload": True,
            "filter": {"must": [{"key": "quality", "match": {"value": quality}}]}}
    response = httpx.post(f"{url}/points/query", json=body, timeout=15)
    response.raise_for_status()
    return [item for item in response.json()["result"]["points"] if item["score"] >= settings.similarity_threshold]
