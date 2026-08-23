"""End-to-end smoke test: fake post -> TTS -> captions -> rendered MP4.

Exercises everything except the Reddit API, so it runs without credentials.

    python scripts/smoke_render.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config, pipeline, render, store  # noqa: E402
from core.reddit import Post, _normalise_title  # noqa: E402

POST = Post(
    id="smoke01",
    subreddit="tifu",
    title=_normalise_title(
        "TIFU by automating my entire damn life with one shell script"
    ),
    body=(
        "This happened last Tuesday and I am still recovering from it. "
        "I have been working from home for about three years now. "
        "Over that time I built up a collection of shell scripts to handle "
        "everything from my morning coffee machine to my standup notes. "
        "My roommate warned me that I was going too far, but I did not listen to her. "
        "Last week I decided to chain all of them together into one master script. "
        "The idea was simple enough. One command would start my whole day. "
        "What I did not account for was the order in which they would run. "
        "The coffee machine script fired before the water line had been opened. "
        "My smart blinds opened at three in the morning instead of seven. "
        "The standup notes were posted to the wrong channel entirely. "
        "By the time I woke up my manager had already replied to them. "
        "He asked why I had submitted a status update about my coffee grinder. "
        "I tried to explain that it was an automation problem. "
        "He said that was somehow worse than having no explanation at all. "
        "The blinds are still opening at three in the morning every single day. "
        "I have not figured out which script is responsible for that one yet."
    ),
    url="https://reddit.com/r/tifu/comments/smoke01",
    comments=[],
)


def main() -> int:
    config.ensure_dirs()
    backgrounds = store.list_backgrounds()
    if not backgrounds:
        print(f"FAIL: no background footage in {config.BACKGROUNDS_DIR}")
        return 1

    print(f"background : {backgrounds[0]}")
    print(f"tts backend: {config.TTS_BACKEND} ({config.PIPER_VOICE})")
    print(f"ffmpeg     : {config.FFMPEG_BIN}")

    started = time.monotonic()
    try:
        parts = pipeline.render_post(
            POST, backgrounds[0], on_progress=lambda m: print(f"  ... {m}")
        )
    except Exception as exc:
        print(f"\nFAIL: {type(exc).__name__}: {exc}")
        return 1

    elapsed = time.monotonic() - started
    print(f"\nrendered {len(parts)} part(s) in {elapsed:.1f}s")
    for part in parts:
        path = config.OUTPUT_DIR / part["file"]
        actual = render.probe_duration(path)
        size_mb = path.stat().st_size / 1e6
        drift = abs(actual - part["seconds"])
        status = "ok" if drift < 1.5 else f"DRIFT {drift:.2f}s"
        print(f"  {part['file']}  {actual:.1f}s  {size_mb:.1f}MB  [{status}]")
        if drift >= 1.5:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
