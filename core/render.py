"""Video composition with plain ffmpeg.

The original used MoviePy + ImageMagick and built one Python object per caption,
which meant an ImageMagick install, a hardcoded Windows path to magick.exe, and
a per-frame Python callback. Here every caption is one line in an ASS subtitle
file and libass draws them, so the whole overlay costs a single filter. ASS also
restores the scale-pop animation that drawtext cannot express.
"""
from __future__ import annotations

import json
import math
import random
import shutil
import struct
import subprocess
from pathlib import Path

from . import config
from .text import wrap_text
from .tts import Caption


class RenderError(RuntimeError):
    pass


_BREW_KEG = "/opt/homebrew/opt/ffmpeg-full/bin"

_SETUP_HINT = (
    "On macOS, Homebrew's plain `ffmpeg` is a minimal build without libass.\n"
    "  brew install ffmpeg-full\n"
    f"It is keg-only, so point the worker at it:\n"
    f"  FFMPEG_BIN={_BREW_KEG}/ffmpeg\n"
    f"  FFPROBE_BIN={_BREW_KEG}/ffprobe\n"
    "On Debian/Ubuntu the stock `ffmpeg` package already includes libass."
)


def _require(binary: str) -> str:
    found = shutil.which(binary) or (binary if Path(binary).is_file() else None)
    if not found:
        raise RenderError(f"'{binary}' not found.\n{_SETUP_HINT}")
    return found


_checked_filters = False


def _require_filters() -> None:
    """Verify once that this ffmpeg build can burn subtitles.

    Without libass the subtitles filter is missing and the render dies with an
    opaque filtergraph parse error, so fail early with something actionable.
    """
    global _checked_filters
    if _checked_filters:
        return
    ffmpeg = _require(config.FFMPEG_BIN)
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True
    )
    if "subtitles" not in result.stdout:
        raise RenderError(
            f"'{ffmpeg}' has no 'subtitles' filter (libass is missing), so "
            f"captions cannot be burned in.\n{_SETUP_HINT}"
        )
    _checked_filters = True


def _run(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-15:])
        raise RenderError(f"{args[0]} failed:\n{tail}")


def probe_duration(path: Path) -> float:
    ffprobe = _require(config.FFPROBE_BIN)
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


BANNER_WIDTH_RATIO = 0.84
# The banner art stacks an avatar row and an awards row above the body text and
# a likes/share row below, so its text area sits below the image's midpoint.
BANNER_TEXT_CENTRE_RATIO = 0.57


def _png_size(path: Path) -> tuple[int, int]:
    """Width/height straight out of the PNG IHDR chunk, so no image library."""
    with open(path, "rb") as handle:
        header = handle.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise RenderError(f"{path} is not a PNG")
    return struct.unpack(">II", header[16:24])


def title_position() -> tuple[int, int]:
    """Centre of the banner's text area, in output-frame coordinates.

    Derived from the banner's real dimensions rather than hardcoded, so
    swapping in different banner art keeps the title correctly seated.
    """
    width, height = _png_size(config.BANNER_IMAGE)
    scaled_height = height * (config.WIDTH * BANNER_WIDTH_RATIO) / width
    top = (config.HEIGHT - scaled_height) / 2
    return config.WIDTH // 2, int(top + scaled_height * BANNER_TEXT_CENTRE_RATIO)


def font_family(ttf: Path) -> str:
    """Family name from the TTF name table; libass matches on that, not filename."""
    from fontTools.ttLib import TTFont

    with TTFont(str(ttf), lazy=True) as font:
        for record in font["name"].names:
            if record.nameID == 1:
                return record.toUnicode()
    raise RenderError(f"no family name in {ttf}")


# --------------------------------------------------------------------------- #
# ASS subtitle generation
# --------------------------------------------------------------------------- #

def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{int(hours)}:{int(minutes):02d}:{secs:05.2f}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


_ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{caption_font},100,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,7,3,5,80,80,80,1
Style: Title,{title_font},46,&H00000000,&H00000000,&H00FFFFFF,&H00FFFFFF,0,0,0,0,100,100,0,0,1,0,0,5,120,120,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# Scale from 70% to 100% over 90ms -- the "pop" the MoviePy version animated.
_POP = r"{\fscx70\fscy70\t(0,90,\fscx100\fscy100)}"

_CAPTION_COLOURS = ["&H00FFFFFF", "&H00FFFF00", "&H0000FFFF", "&H00FF00FF"]


def write_ass(
    path: Path,
    title: str,
    title_duration: float,
    captions: list[Caption],
    span: tuple[float, float],
    colour_cycle: list[float] | None = None,
) -> None:
    """Write one part's subtitles, rebased onto that part's own timeline.

    A part plays the title card for `title_duration`, then narration from
    span[0] to span[1]. A caption at narration time `c` therefore lands at
    video time `title_duration + (c - span[0])`.

    `colour_cycle` holds boundary times (used for AskReddit comment changes);
    captions after each boundary advance to the next colour.
    """
    start, end = span
    lines = [
        _ASS_HEADER.format(
            width=config.WIDTH,
            height=config.HEIGHT,
            caption_font=font_family(config.CAPTION_FONT),
            title_font=font_family(config.TITLE_FONT),
        )
    ]

    wrapped = _ass_escape(wrap_text(title, 34)).replace("\n", r"\N")
    title_x, title_y = title_position()
    lines.append(
        f"Dialogue: 0,{_ass_time(0)},{_ass_time(title_duration)},Title,,0,0,0,,"
        f"{{\\an5\\pos({title_x},{title_y})}}{wrapped}"
    )

    for caption in captions:
        if caption.end <= start or caption.start >= end:
            continue
        colour = ""
        if colour_cycle:
            index = sum(1 for boundary in colour_cycle if boundary <= caption.start)
            colour = f"\\c{_CAPTION_COLOURS[index % len(_CAPTION_COLOURS)]}"
        text = _ass_escape(caption.text.upper())
        rebased_start = title_duration + max(caption.start, start) - start
        rebased_end = title_duration + min(caption.end, end) - start
        lines.append(
            f"Dialogue: 0,{_ass_time(rebased_start)},{_ass_time(rebased_end)},"
            f"Caption,,0,0,0,,{{\\an5{colour}}}{_POP}{text}"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# splitting
# --------------------------------------------------------------------------- #

def plan_parts(captions: list[Caption], title_duration: float) -> list[tuple[float, float]]:
    """Cut the narration into shorts-length spans, never mid-caption."""
    if not captions:
        return []

    budget = config.MAX_SHORT_SECONDS - title_duration
    if budget <= 5:
        raise RenderError(
            f"Title narration is {title_duration:.1f}s, leaving no room in a "
            f"{config.MAX_SHORT_SECONDS:.0f}s short. Use a shorter title."
        )

    # Greedy packing leaves a stub tail -- 58s + 4s instead of two 31s halves.
    # The total is known up front, so choose a part count and divide evenly,
    # snapping each cut to the nearest caption boundary.
    total = captions[-1].end
    if total <= budget:
        return [(0.0, total)]

    cuts = [caption.end for caption in captions[:-1]]
    minimum = math.ceil(total / budget)
    # Cuts only land on caption boundaries, so the ideal count is not always
    # achievable -- 102s of 2s captions cannot be two parts of 51s. Escalate
    # until a feasible split exists rather than emitting an over-length part.
    for count in range(minimum, minimum + 5):
        spans = _split_into(cuts, total, budget, count)
        if spans is not None:
            return spans
    raise RenderError(
        f"Cannot split {total:.1f}s of narration into parts of at most "
        f"{budget:.1f}s on caption boundaries."
    )


def _split_into(
    cuts: list[float], total: float, budget: float, count: int
) -> list[tuple[float, float]] | None:
    """Try to divide into exactly `count` parts. None if no cut placement fits."""
    spans: list[tuple[float, float]] = []
    start = 0.0
    for index in range(1, count):
        ideal = total * index / count
        remaining = count - index
        feasible = [
            c for c in cuts
            if start < c < total
            and c - start <= budget           # this part fits
            and total - c <= budget * remaining  # the rest can still fit
        ]
        if not feasible:
            return None
        cut = min(feasible, key=lambda c: (abs(c - ideal), c))
        spans.append((start, cut))
        start = cut
    if total - start > budget:
        return None
    spans.append((start, total))
    return spans


# --------------------------------------------------------------------------- #
# composition
# --------------------------------------------------------------------------- #

def _background_offset(background: Path, needed: float) -> float:
    total = probe_duration(background)
    if total <= needed:
        return 0.0
    return random.uniform(0, total - needed)


def compose(
    background: Path,
    narration_wav: Path,
    title_wav: Path,
    ass_file: Path,
    out_path: Path,
    span: tuple[float, float],
    title_duration: float,
) -> Path:
    """Render one part: title card, then narration with captions burned in."""
    _require_filters()
    start, end = span
    body_duration = end - start
    total = title_duration + body_duration
    offset = _background_offset(background, total)

    # The ASS file is already rebased onto this part's timeline by write_ass,
    # so the subtitle filter needs no PTS manipulation.
    filtergraph = (
        f"[0:v]scale={config.WIDTH}:{config.HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={config.WIDTH}:{config.HEIGHT},fps={config.FPS},setpts=PTS-STARTPTS[bg];"
        f"[1:v]scale={int(config.WIDTH * BANNER_WIDTH_RATIO)}:-1[banner];"
        f"[bg][banner]overlay=(W-w)/2:(H-h)/2:enable='lt(t,{title_duration:.3f})'[card];"
        f"[card]subtitles=filename='{ass_file.as_posix()}'"
        f":fontsdir='{config.CAPTION_FONT.parent.as_posix()}'[vout];"
        f"[2:a]atrim=0:{title_duration:.3f},asetpts=PTS-STARTPTS[atitle];"
        f"[3:a]atrim={start:.3f}:{end:.3f},asetpts=PTS-STARTPTS[abody];"
        f"[atitle][abody]concat=n=2:v=0:a=1,loudnorm=I=-14:TP=-1.5:LRA=11[aout]"
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        config.FFMPEG_BIN, "-y", "-loglevel", "error",
        "-stream_loop", "-1", "-ss", f"{offset:.3f}", "-t", f"{total:.3f}", "-i", str(background),
        "-i", str(config.BANNER_IMAGE),
        "-i", str(title_wav),
        "-i", str(narration_wav),
        "-filter_complex", filtergraph,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
        "-shortest", "-movflags", "+faststart",
        str(out_path),
    ])
    return out_path
