"""Persistent job metadata. Only the API service opens this database."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from .config import settings

class JobStore:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = Lock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, data TEXT NOT NULL)")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, **fields) -> dict:
        job_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        job = {
            "job_id": job_id,
            "status": "queued",
            "log": "",
            "error": None,
            "video_url": None,
            "code": None,
            "created_at": now,
            "updated_at": now,
            **fields,
        }
        with self._lock, self._connect() as db:
            db.execute("INSERT INTO jobs VALUES (?, ?)", (job_id, json.dumps(job)))
        return job

    def get(self, job_id: str) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT data FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def update(self, job_id: str, **fields) -> dict | None:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT data FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if not row:
                return None
            job = json.loads(row[0])
            job.update(fields)
            job["updated_at"] = datetime.now(timezone.utc).isoformat()
            db.execute("UPDATE jobs SET data = ? WHERE job_id = ?", (json.dumps(job), job_id))
        return job

    def unfinished(self) -> list[dict]:
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT data FROM jobs").fetchall()
        return [job for (raw,) in rows if (job := json.loads(raw))["status"] in {"queued", "running"}]


store = JobStore(settings.database_path)
