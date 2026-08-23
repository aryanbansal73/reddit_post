"""Vercel entrypoint: the public web app.

Deliberately thin. It renders the UI and forwards job control to the render
worker running on your machine. It never touches media -- Vercel functions have
a read-only filesystem, a 4.5 MB request body cap and a hard execution timeout,
none of which suit encoding 1080x1920 video.

Vercel auto-detects this file and the top-level `app` object.
"""
from __future__ import annotations

import os

import requests
from flask import Flask, abort, jsonify, redirect, render_template, request, url_for

app = Flask(__name__)

WORKER_URL = os.environ.get("WORKER_URL", "http://localhost:8000").rstrip("/")
WORKER_TOKEN = os.environ.get("WORKER_TOKEN", "")
CRON_SECRET = os.environ.get("CRON_SECRET", "")
TIMEOUT = 15


class WorkerOffline(RuntimeError):
    pass


def worker(method: str, path: str, **kwargs):
    """Call the render worker, translating transport failures into a clear error."""
    try:
        response = requests.request(
            method,
            f"{WORKER_URL}{path}",
            headers={"Authorization": f"Bearer {WORKER_TOKEN}"},
            timeout=TIMEOUT,
            **kwargs,
        )
    except requests.RequestException as exc:
        raise WorkerOffline(
            "The render worker is not reachable. Start it with `python worker.py` "
            "and make sure its tunnel is up."
        ) from exc
    if response.status_code >= 400:
        detail = response.json().get("message") if _is_json(response) else response.text
        abort(response.status_code, detail or "worker error")
    return response.json()


def _is_json(response: requests.Response) -> bool:
    return response.headers.get("content-type", "").startswith("application/json")


@app.errorhandler(WorkerOffline)
def handle_offline(exc: WorkerOffline):
    if request.path.startswith("/api/"):
        return jsonify(error=str(exc)), 503
    return render_template("error.html", message=str(exc)), 503


# --------------------------------------------------------------------------- #
# pages
# --------------------------------------------------------------------------- #

@app.get("/")
def index():
    try:
        health = worker("GET", "/health")
        backgrounds, online = health.get("backgrounds", []), True
    except WorkerOffline:
        backgrounds, online = [], False
    return render_template("index.html", backgrounds=backgrounds, online=online)


@app.post("/submit")
def submit():
    url = (request.form.get("url") or "").strip()
    if not url:
        return render_template("error.html", message="Paste a Reddit post URL first."), 400
    job = worker("POST", "/jobs", json={
        "kind": "post",
        "url": url,
        "background": request.form.get("background") or None,
    })
    return redirect(url_for("job_page", job_id=job["id"]))


@app.post("/submit-batch")
def submit_batch():
    subreddits = [s.strip() for s in (request.form.get("subreddits") or "").split(",") if s.strip()]
    job = worker("POST", "/jobs", json={
        "kind": "batch",
        "subreddits": subreddits or None,
        "background": request.form.get("background") or None,
    })
    return redirect(url_for("job_page", job_id=job["id"]))


@app.get("/jobs/<job_id>")
def job_page(job_id: str):
    return render_template("job.html", job_id=job_id, worker_url=WORKER_URL)


@app.get("/dashboard")
def dashboard():
    try:
        jobs = worker("GET", "/jobs").get("jobs", [])
        online = True
    except WorkerOffline:
        jobs, online = [], False
    return render_template("dashboard.html", jobs=jobs, online=online, worker_url=WORKER_URL)


# --------------------------------------------------------------------------- #
# json api (polled by the job page)
# --------------------------------------------------------------------------- #

@app.get("/api/jobs/<job_id>")
def api_job(job_id: str):
    return jsonify(worker("GET", f"/jobs/{job_id}"))


@app.get("/api/health")
def api_health():
    return jsonify(worker("GET", "/health"))


@app.get("/api/cron/daily")
def cron_daily():
    """Triggered by Vercel Cron, which signs the request with CRON_SECRET.

    Fails closed when the secret is unset: this endpoint queues real work on a
    public domain, so an unconfigured deployment must not leave it open.
    """
    if not CRON_SECRET:
        abort(503, "CRON_SECRET is not configured; refusing to run unauthenticated")
    if request.headers.get("Authorization") != f"Bearer {CRON_SECRET}":
        abort(401)
    return jsonify(worker("POST", "/jobs", json={"kind": "batch"})), 202
