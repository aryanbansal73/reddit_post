"""End-to-end: Reddit post -> narrated, captioned vertical video parts."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from . import config, reddit, render, store, tts
from .text import slugify_title

Progress = Callable[[str], None]


def _noop(_: str) -> None:
    pass


def render_post(
    post: reddit.Post,
    background_name: str,
    on_progress: Progress = _noop,
) -> list[dict]:
    """Synthesize, caption and render one post. Returns metadata per part."""
    config.ensure_dirs()
    background = store.background_path(background_name)
    slug = f"{post.subreddit}_{post.id}_{slugify_title(post.title)}"
    work = config.WORK_DIR / slug
    work.mkdir(parents=True, exist_ok=True)

    try:
        on_progress("synthesising title")
        title_wav = work / "title.wav"
        tts.synthesize(post.title, title_wav, work / "title_parts")
        title_duration = tts.duration_of(title_wav)

        on_progress("synthesising narration")
        narration_wav = work / "narration.wav"
        captions = tts.synthesize(post.narration, narration_wav, work / "body_parts")
        if not captions:
            raise render.RenderError("narration produced no captions")

        colour_cycle = _comment_boundaries(post, captions) if post.comments else None

        spans = render.plan_parts(captions, title_duration)
        on_progress(f"rendering {len(spans)} part(s)")

        results = []
        for index, span in enumerate(spans, start=1):
            suffix = f"_p{index}" if len(spans) > 1 else ""
            ass_file = work / f"part{index}.ass"
            render.write_ass(
                ass_file, post.title, title_duration, captions, span, colour_cycle
            )
            out_path = config.OUTPUT_DIR / f"{slug}{suffix}.mp4"
            on_progress(f"rendering part {index}/{len(spans)}")
            render.compose(
                background=background,
                narration_wav=narration_wav,
                title_wav=title_wav,
                ass_file=ass_file,
                out_path=out_path,
                span=span,
                title_duration=title_duration,
            )
            results.append({
                "file": out_path.name,
                "part": index,
                "of": len(spans),
                "seconds": round(title_duration + (span[1] - span[0]), 1),
            })
        return results
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _comment_boundaries(post: reddit.Post, captions: list[tts.Caption]) -> list[float]:
    """Times at which the narration moves to the next AskReddit comment.

    Located by matching each comment's opening caption text, which avoids the
    old approach of writing a comment_times.txt sidecar file and re-reading it.
    """
    boundaries: list[float] = []
    cursor = 0
    for comment in post.comments[1:]:
        head = " ".join(comment.split()[:2]).lower()
        for index in range(cursor, len(captions)):
            if captions[index].text.lower().startswith(head[: len(captions[index].text)]):
                boundaries.append(captions[index].start)
                cursor = index + 1
                break
    return boundaries


def run_job(job: dict, on_progress: Progress = _noop) -> dict:
    """Execute a queued job. Raises on failure; the caller records it."""
    payload = job["payload"]
    background = payload.get("background") or _default_background()

    if job["kind"] == "post":
        on_progress("fetching post")
        post = reddit.fetch_post(payload["url"])
        parts = render_post(post, background, on_progress)
        return {"posts": [{"title": post.title, "url": post.url, "parts": parts}]}

    if job["kind"] == "batch":
        on_progress("fetching top posts")
        posts = reddit.fetch_batch(
            payload.get("subreddits"), payload.get("per_subreddit")
        )
        rendered = []
        for index, post in enumerate(posts, start=1):
            on_progress(f"post {index}/{len(posts)}: {post.title[:50]}")
            try:
                parts = render_post(post, background, on_progress)
            except Exception as exc:  # one bad post must not sink the batch
                rendered.append({"title": post.title, "url": post.url, "error": str(exc)})
                continue
            rendered.append({"title": post.title, "url": post.url, "parts": parts})
        return {"posts": rendered}

    raise ValueError(f"unknown job kind '{job['kind']}'")


def _default_background() -> str:
    available = store.list_backgrounds()
    if not available:
        raise FileNotFoundError(
            f"No background footage. Upload one, or drop an mp4 in "
            f"{config.BACKGROUNDS_DIR}"
        )
    return available[0]
