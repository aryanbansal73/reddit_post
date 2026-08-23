"""Free, offline speech synthesis that emits caption timings as a by-product.

The old pipeline synthesised one big WAV and then ran `whisper_timestamped`
(PyTorch + a 140MB model) over that WAV to recover word timings -- timings that
were destroyed on the way out of the synthesiser. Here the audio is built one
sentence at a time, so each sentence's duration is known exactly from its own
WAV header, and captions fall out for free. No ASR model, no PyTorch, no GPU.

Two backends:
  piper  -- fully offline, no API key, no quota. Sentence-exact timings, word
            timings interpolated inside a sentence by syllable weight.
  edge   -- Microsoft Edge's read-aloud voices. Free and higher quality, but an
            undocumented endpoint. Returns true word boundaries.
"""
from __future__ import annotations

import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

from . import config
from .text import chunk_for_captions, estimate_syllables, expand_abbreviations, split_sentences

SENTENCE_GAP_SECONDS = 0.12


@dataclass
class Caption:
    text: str
    start: float
    end: float


class TTSError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# piper
# --------------------------------------------------------------------------- #

_voice_cache: dict[str, object] = {}


def _load_piper_voice():
    """Load the ONNX voice once per process; model load dominates synth cost."""
    name = config.PIPER_VOICE
    if name in _voice_cache:
        return _voice_cache[name]

    try:
        from piper import PiperVoice
    except ImportError as exc:  # pragma: no cover - install-time failure
        raise TTSError(
            "piper-tts is not installed. Run: pip install -r requirements-worker.txt"
        ) from exc

    model = config.PIPER_VOICES_DIR / f"{name}.onnx"
    if not model.exists():
        raise TTSError(
            f"Voice '{name}' not found at {model}.\n"
            f"Download it with:\n"
            f"  python -m piper.download_voices {name} --data-dir {config.PIPER_VOICES_DIR}"
        )

    voice = PiperVoice.load(str(model))
    _voice_cache[name] = voice
    return voice


def _piper_write(voice, text: str, path: Path) -> None:
    """Write one sentence to a WAV, tolerating both piper 1.x API shapes."""
    with wave.open(str(path), "wb") as wav:
        if hasattr(voice, "synthesize_wav"):
            voice.synthesize_wav(text, wav)
        else:  # piper < 1.3
            voice.synthesize(text, wav)


def _wav_params(path: Path) -> tuple:
    with wave.open(str(path), "rb") as wav:
        return wav.getparams()


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / float(wav.getframerate())


def _concat_wavs(parts: list[Path], out_path: Path, gap: float) -> None:
    """Join same-format WAVs with a silent gap. No pydub, no ffmpeg, no numpy."""
    if not parts:
        raise TTSError("nothing to concatenate")

    params = _wav_params(parts[0])
    silence = b"\x00" * int(params.framerate * gap) * params.sampwidth * params.nchannels

    with wave.open(str(out_path), "wb") as out:
        out.setparams(params)
        for index, part in enumerate(parts):
            if index:
                out.writeframes(silence)
            with wave.open(str(part), "rb") as src:
                out.writeframes(src.readframes(src.getnframes()))


def _captions_for_sentence(sentence: str, start: float, duration: float) -> list[Caption]:
    """Spread a known sentence duration across its caption chunks.

    Weighted by syllables rather than characters, so "strength" (1 beat) does
    not steal time from "banana" (3). Error never escapes a single sentence.
    """
    chunks = chunk_for_captions(sentence)
    if not chunks:
        return []

    weights = [sum(estimate_syllables(w) for w in chunk.split()) for chunk in chunks]
    total = sum(weights) or len(chunks)

    captions, cursor = [], start
    for chunk, weight in zip(chunks, weights):
        span = duration * (weight / total)
        captions.append(Caption(text=chunk, start=cursor, end=cursor + span))
        cursor += span
    # Absorb float drift into the final chunk so it lands exactly on the end.
    captions[-1].end = start + duration
    return captions


def _synthesize_piper(text: str, out_wav: Path, work_dir: Path) -> list[Caption]:
    voice = _load_piper_voice()
    sentences = split_sentences(expand_abbreviations(text))
    if not sentences:
        raise TTSError("no speakable text")

    parts: list[Path] = []
    captions: list[Caption] = []
    cursor = 0.0

    for index, sentence in enumerate(sentences):
        part = work_dir / f"sent_{index:04d}.wav"
        _piper_write(voice, sentence, part)
        duration = _wav_duration(part)
        if duration <= 0:
            part.unlink(missing_ok=True)
            continue
        captions.extend(_captions_for_sentence(sentence, cursor, duration))
        cursor += duration + SENTENCE_GAP_SECONDS
        parts.append(part)

    _concat_wavs(parts, out_wav, SENTENCE_GAP_SECONDS)
    for part in parts:
        part.unlink(missing_ok=True)
    return captions


# --------------------------------------------------------------------------- #
# edge-tts
# --------------------------------------------------------------------------- #


def _synthesize_edge(text: str, out_wav: Path, work_dir: Path) -> list[Caption]:
    import asyncio

    try:
        import edge_tts
    except ImportError as exc:
        raise TTSError("edge-tts is not installed. pip install edge-tts") from exc

    text = expand_abbreviations(text)
    mp3_path = work_dir / "edge.mp3"
    boundaries: list[tuple[str, float, float]] = []

    async def run() -> None:
        communicate = edge_tts.Communicate(text, config.EDGE_VOICE)
        with open(mp3_path, "wb") as handle:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    handle.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / 1e7  # 100ns ticks -> seconds
                    boundaries.append((chunk["text"], start, start + chunk["duration"] / 1e7))

    asyncio.run(run())

    subprocess.run(
        [config.FFMPEG_BIN, "-y", "-loglevel", "error", "-i", str(mp3_path),
         "-ac", "1", "-ar", "22050", str(out_wav)],
        check=True,
    )
    mp3_path.unlink(missing_ok=True)

    # Regroup true word boundaries into on-screen caption chunks.
    captions: list[Caption] = []
    buffer: list[tuple[str, float, float]] = []
    for word, start, end in boundaries:
        candidate = " ".join(w for w, _, _ in buffer + [(word, start, end)])
        if buffer and len(candidate) > 15:
            captions.append(Caption(" ".join(w for w, _, _ in buffer), buffer[0][1], buffer[-1][2]))
            buffer = [(word, start, end)]
        else:
            buffer.append((word, start, end))
    if buffer:
        captions.append(Caption(" ".join(w for w, _, _ in buffer), buffer[0][1], buffer[-1][2]))
    return captions


# --------------------------------------------------------------------------- #


def synthesize(text: str, out_wav: Path, work_dir: Path) -> list[Caption]:
    """Render `text` to `out_wav` and return caption timings in seconds."""
    work_dir.mkdir(parents=True, exist_ok=True)
    out_wav.parent.mkdir(parents=True, exist_ok=True)

    backend = config.TTS_BACKEND.lower()
    if backend == "piper":
        return _synthesize_piper(text, out_wav, work_dir)
    if backend == "edge":
        return _synthesize_edge(text, out_wav, work_dir)
    raise TTSError(f"unknown TTS_BACKEND '{backend}' (expected 'piper' or 'edge')")


def duration_of(path: Path) -> float:
    return _wav_duration(path)
