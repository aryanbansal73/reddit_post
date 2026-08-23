"""SQLite-backed job queue and local output storage.

Everything lives on the worker machine's disk. SQLite is enough: this is a
single-worker queue with a handful of jobs a day, so a database server would be
more moving parts than the problem has.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import config

QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    status      TEXT NOT NULL,
    payload     TEXT NOT NULL,
    result      TEXT,
    error       TEXT,
    progress    TEXT,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_status_created ON jobs(status, created_at);
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    job = dict(row)
    job["payload"] = json.loads(job["payload"])
    job["result"] = json.loads(job["result"]) if job["result"] else None
    return job


def enqueue(kind: str, payload: dict[str, Any]) -> str:
    job_id = uuid.uuid4().hex[:12]
    now = time.time()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, kind, status, payload, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, kind, QUEUED, json.dumps(payload), now, now),
        )
    return job_id


def claim_next() -> dict[str, Any] | None:
    """Atomically move the oldest queued job to running and return it."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY created_at LIMIT 1", (QUEUED,)
        ).fetchone()
        if row is None:
            return None
        changed = conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ? AND status = ?",
            (RUNNING, time.time(), row["id"], QUEUED),
        ).rowcount
        if changed == 0:
            return None
        return _row_to_dict(row)


def set_progress(job_id: str, message: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET progress = ?, updated_at = ? WHERE id = ?",
            (message, time.time(), job_id),
        )


def finish(job_id: str, result: dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, result = ?, progress = NULL, updated_at = ?"
            " WHERE id = ?",
            (DONE, json.dumps(result), time.time(), job_id),
        )


def fail(job_id: str, error: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, error = ?, progress = NULL, updated_at = ?"
            " WHERE id = ?",
            (FAILED, error[:2000], time.time(), job_id),
        )


def get(job_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_dict(row) if row else None


def recent(limit: int = 25) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_row_to_dict(row) for row in rows]


def requeue_stale(older_than: float = 3600) -> int:
    """Recover jobs left running by a worker that died mid-render."""
    cutoff = time.time() - older_than
    with _connect() as conn:
        return conn.execute(
            "UPDATE jobs SET status = ? WHERE status = ? AND updated_at < ?",
            (QUEUED, RUNNING, cutoff),
        ).rowcount


# --------------------------------------------------------------------------- #
# background footage
# --------------------------------------------------------------------------- #

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm"}


def list_backgrounds() -> list[str]:
    config.ensure_dirs()
    return sorted(
        p.name for p in config.BACKGROUNDS_DIR.iterdir()
        if p.suffix.lower() in VIDEO_SUFFIXES
    )


def background_path(name: str) -> Path:
    """Resolve a background by name, refusing anything outside the directory."""
    config.ensure_dirs()
    candidate = (config.BACKGROUNDS_DIR / Path(name).name).resolve()
    if candidate.parent != config.BACKGROUNDS_DIR.resolve() or not candidate.exists():
        raise FileNotFoundError(f"background '{name}' not found")
    return candidate


def output_path(name: str) -> Path:
    candidate = (config.OUTPUT_DIR / Path(name).name).resolve()
    if candidate.parent != config.OUTPUT_DIR.resolve() or not candidate.exists():
        raise FileNotFoundError(f"output '{name}' not found")
    return candidate
