"""Local render worker: HTTP API + a background thread that drains the queue.

Runs on your own machine, where ffmpeg, the Piper voice and the (large)
background footage live. Expose it with a Cloudflare Tunnel so the Vercel app
can reach it:

    cloudflared tunnel --url http://localhost:8000

Start it with:

    python worker.py
"""
from __future__ import annotations

import logging
import threading
import time
from functools import wraps

from flask import Flask, abort, jsonify, request, send_from_directory

from core import config, pipeline, store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2 GB background uploads

POLL_SECONDS = 3


def require_token(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not config.WORKER_TOKEN:
            abort(500, "WORKER_TOKEN is not set on the worker")
        header = request.headers.get("Authorization", "")
        if header != f"Bearer {config.WORKER_TOKEN}":
            abort(401, "bad or missing worker token")
        return view(*args, **kwargs)

    return wrapper


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #

@app.get("/health")
def health():
    return jsonify(
        ok=True,
        backgrounds=store.list_backgrounds(),
        tts_backend=config.TTS_BACKEND,
        voice=config.PIPER_VOICE,
    )


@app.post("/jobs")
@require_token
def create_job():
    body = request.get_json(silent=True) or {}
    kind = body.get("kind", "post")
    if kind not in ("post", "batch"):
        abort(400, "kind must be 'post' or 'batch'")
    if kind == "post" and not body.get("url"):
        abort(400, "a Reddit post url is required")

    payload = {k: v for k, v in body.items() if k != "kind"}
    job_id = store.enqueue(kind, payload)
    log.info("queued %s job %s", kind, job_id)
    return jsonify(id=job_id, status=store.QUEUED), 202


@app.get("/jobs/<job_id>")
@require_token
def read_job(job_id: str):
    job = store.get(job_id)
    if job is None:
        abort(404, "no such job")
    return jsonify(job)


@app.get("/jobs")
@require_token
def list_jobs():
    return jsonify(jobs=store.recent())


@app.get("/backgrounds")
@require_token
def list_backgrounds():
    return jsonify(backgrounds=store.list_backgrounds())


@app.post("/backgrounds")
@require_token
def upload_background():
    """Background footage is uploaded straight here, never through Vercel.

    Vercel functions cap request bodies at 4.5 MB, so gameplay footage cannot
    transit the web app; it goes directly to the worker's disk.
    """
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        abort(400, "no file part named 'file'")

    name = "".join(
        c for c in upload.filename if c.isalnum() or c in "._- "
    ).strip().replace(" ", "_")
    if not name or not name.lower().endswith(tuple(store.VIDEO_SUFFIXES)):
        abort(400, f"filename must end with one of {sorted(store.VIDEO_SUFFIXES)}")

    config.ensure_dirs()
    upload.save(config.BACKGROUNDS_DIR / name)
    log.info("stored background %s", name)
    return jsonify(saved=name, backgrounds=store.list_backgrounds()), 201


@app.get("/files/<path:name>")
def serve_output(name: str):
    """Rendered videos, served from local disk. Unauthenticated by design:
    filenames carry a Reddit post id, and the web app links straight here."""
    try:
        path = store.output_path(name)
    except FileNotFoundError:
        abort(404)
    return send_from_directory(path.parent, path.name, conditional=True)


# --------------------------------------------------------------------------- #
# queue drain
# --------------------------------------------------------------------------- #

def drain_queue(stop: threading.Event) -> None:
    store.init()
    store.requeue_stale()
    while not stop.is_set():
        job = store.claim_next()
        if job is None:
            stop.wait(POLL_SECONDS)
            continue

        log.info("running job %s (%s)", job["id"], job["kind"])
        started = time.monotonic()
        try:
            result = pipeline.run_job(
                job, on_progress=lambda msg: store.set_progress(job["id"], msg)
            )
            store.finish(job["id"], result)
            log.info("job %s done in %.1fs", job["id"], time.monotonic() - started)
        except Exception as exc:
            log.exception("job %s failed", job["id"])
            store.fail(job["id"], f"{type(exc).__name__}: {exc}")


def start_worker_thread() -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=drain_queue, args=(stop,), daemon=True).start()
    return stop


if __name__ == "__main__":
    config.ensure_dirs()
    store.init()
    if not config.WORKER_TOKEN:
        log.warning("WORKER_TOKEN is unset - the job API will refuse every request")
    start_worker_thread()
    app.run(host="0.0.0.0", port=8000, threaded=True, use_reloader=False)
