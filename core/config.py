"""Runtime configuration, read from the environment once at import."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- storage (all local; nothing leaves the worker machine) -------------------
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
BACKGROUNDS_DIR = DATA_DIR / "backgrounds"
OUTPUT_DIR = DATA_DIR / "output"
WORK_DIR = DATA_DIR / "work"
DB_PATH = DATA_DIR / "jobs.db"

# --- reddit (script-type OAuth app: https://reddit.com/prefs/apps) -----------
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.environ.get("REDDIT_USER_AGENT", "reddit_post/2.0")

# --- tts ---------------------------------------------------------------------
TTS_BACKEND = os.environ.get("TTS_BACKEND", "piper")
PIPER_VOICE = os.environ.get("PIPER_VOICE", "en_US-hfc_male-medium")
PIPER_VOICES_DIR = Path(os.environ.get("PIPER_VOICES_DIR", DATA_DIR / "voices"))
EDGE_VOICE = os.environ.get("EDGE_VOICE", "en-US-GuyNeural")

# --- video -------------------------------------------------------------------
# Homebrew's plain `ffmpeg` formula is a minimal build without libass, and
# `ffmpeg-full` is keg-only (never symlinked onto PATH). Point these at it.
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE_BIN = os.environ.get("FFPROBE_BIN", "ffprobe")

WIDTH, HEIGHT, FPS = 1080, 1920, 30
MAX_SHORT_SECONDS = float(os.environ.get("MAX_SHORT_SECONDS", 59))
CAPTION_FONT = ROOT / "static" / "fonts" / "GILBI___.TTF"
TITLE_FONT = ROOT / "static" / "fonts" / "ARLRDBD.TTF"
BANNER_IMAGE = ROOT / "static" / "images" / "medalled_banner_resized.png"
COMMENT_IMAGE = ROOT / "static" / "images" / "comments.png"

# --- post selection ----------------------------------------------------------
MIN_POST_CHARS = int(os.environ.get("MIN_POST_CHARS", 900))
MAX_POST_CHARS = int(os.environ.get("MAX_POST_CHARS", 2300))
MAX_COMMENTS = int(os.environ.get("MAX_COMMENTS", 8))
DAILY_SUBREDDITS = [
    s.strip()
    for s in os.environ.get(
        "DAILY_SUBREDDITS", "relationship_advice,tifu,AmItheAsshole"
    ).split(",")
    if s.strip()
]
DAILY_POSTS_PER_SUB = int(os.environ.get("DAILY_POSTS_PER_SUB", 2))

# --- worker <-> web ----------------------------------------------------------
WORKER_TOKEN = os.environ.get("WORKER_TOKEN", "")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")


def ensure_dirs() -> None:
    for d in (DATA_DIR, BACKGROUNDS_DIR, OUTPUT_DIR, WORK_DIR, PIPER_VOICES_DIR):
        d.mkdir(parents=True, exist_ok=True)
