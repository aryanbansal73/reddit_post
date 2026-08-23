# reddit_post

Turns Reddit self-posts into narrated, captioned vertical videos for Shorts /
Reels / TikTok. Runs on-demand from a web page, or as a scheduled daily batch.

No paid APIs. Speech synthesis is offline (Piper), and there is no
speech-to-text step at all.

---

## Architecture

Vercel functions cannot encode video — read-only filesystem, 4.5 MB request
bodies, a hard execution timeout, and a bundle limit that PyTorch alone would
blow. So the work is split:

```
  yourdomain.com          Vercel        app.py      UI + job control (flask + requests only)
        |
        |  HTTPS, bearer token
        v
  worker.yourdomain.com   your Mac      worker.py   queue, TTS, ffmpeg, local disk
                                        core/       the actual pipeline
```

The worker holds the job queue (SQLite), the gameplay footage, the voice model
and the rendered output. Vercel never touches media; it queues jobs, polls
status, and links to files the worker serves.

### Pipeline

```
Reddit OAuth API  ->  clean text  ->  Piper TTS (per sentence)  ->  ASS subtitles  ->  ffmpeg
                                          |                              |
                                    exact durations  ------------->  caption timings
```

**There is no speech-to-text.** The old pipeline synthesised one long WAV and
then ran `whisper_timestamped` (PyTorch + a 140 MB model) over it to recover
word timings — timings that were destroyed on the way *out* of the synthesiser.
Synthesising one sentence at a time makes each duration exactly readable from
its own WAV header, so captions fall out for free. Inside a sentence, chunk
timings are interpolated by syllable weight; drift never escapes one sentence.

If you switch to `TTS_BACKEND=edge`, you get true word boundaries from the
service itself, and even the interpolation goes away.

---

## Setup

### 1. Reddit API credentials

Create a free **script** app at <https://www.reddit.com/prefs/apps>. You need
the client id and secret — no username or password, and no browser automation.

### 2. ffmpeg with libass

Captions are burned in by libass via the `subtitles` filter.

**macOS** — Homebrew's plain `ffmpeg` formula is a *minimal* build without
libass. You need `ffmpeg-full`, which is keg-only (never symlinked onto PATH):

```bash
brew install ffmpeg-full
```

Then point the worker at it in `.env`:

```
FFMPEG_BIN=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg
FFPROBE_BIN=/opt/homebrew/opt/ffmpeg-full/bin/ffprobe
```

**Debian/Ubuntu** — the stock `ffmpeg` package already includes libass; leave
`FFMPEG_BIN` unset.

The worker checks for the `subtitles` filter at startup of the first render and
tells you exactly what is missing if it is not there.

### 3. Worker environment

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-worker.txt
.venv/bin/python -m piper.download_voices en_US-hfc_male-medium --data-dir ./data/voices
cp .env.example .env    # then fill it in
```

Generate the shared token:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 4. Background footage

Drop MP4s into `data/backgrounds/`, or upload them to the running worker:

```bash
curl -H "Authorization: Bearer $WORKER_TOKEN" -F file=@gameplay.mp4 http://localhost:8000/backgrounds
```

Uploads go **directly to the worker**, never through Vercel — a Vercel function
caps request bodies at 4.5 MB, which no gameplay clip will fit under.

Footage is looped and randomly seeked, so one long clip is enough.

### 5. Run it

```bash
.venv/bin/python worker.py          # http://localhost:8000
```

Check it end to end without touching Reddit:

```bash
.venv/bin/python scripts/smoke_render.py
```

---

## Deploying the web app

### Expose the worker

Vercel needs to reach your machine, and the worker needs a URL that does not
change every restart (it is stored as `WORKER_URL` in Vercel's env).

**ngrok** (free plan gives one assigned dev domain):

```bash
brew install ngrok
ngrok config add-authtoken <token from dashboard.ngrok.com>
ngrok http 8000 --url <your-assigned-domain>.ngrok-free.app
```

Then set `WORKER_URL` on Vercel to `https://<your-assigned-domain>.ngrok-free.app`.

Two free-plan limits worth knowing:

- **Interstitial page.** ngrok shows a click-through warning on HTTP endpoints.
  The web app sends `ngrok-skip-browser-warning` so the JSON API is unaffected,
  but the *first* rendered-video link you open in a given browser will show it
  once before ngrok sets its cookie.
- **1 GB/month transfer.** Parts are 10–20 MB, so roughly 50–100 downloads a
  month. Fine for personal use; it is the first thing you will outgrow.

**Why not a Cloudflare named tunnel?** It needs the domain on Cloudflare's
nameservers, and `brogrammerlabs.com` is on Squarespace DNS. A
`*.cfargotunnel.com` CNAME only resolves behind Cloudflare's proxy, so it cannot
be pointed at from third-party DNS. Moving nameservers to Cloudflare would work
and would give you a real `worker.brogrammerlabs.com`, at the cost of
re-creating the existing Vercel records there.

**Tailscale Funnel** is the other free option with a stable URL and no
interstitial or bandwidth cap, if ngrok's limits start to bite.

### Ship to Vercel

```bash
npx vercel deploy --prod
```

Vercel auto-detects `app.py` and its top-level `app`. Set these project env vars:

| Variable | Value |
|---|---|
| `WORKER_URL` | `https://worker.yourdomain.com` |
| `WORKER_TOKEN` | same value as the worker's |
| `CRON_SECRET` | any long random string |

`CRON_SECRET` is required. `/api/cron/daily` refuses to run without it rather
than leaving a job-queueing endpoint open on a public domain.

Attach your domain in the Vercel dashboard under **Settings → Domains**.

`vercel.json` registers the daily batch at 13:00 UTC. Hobby plans allow two
cron jobs, once per day each.

### When the Mac is asleep

The site stays up and degrades honestly — it shows a "worker offline" banner and
disables the forms rather than accepting jobs it cannot run.

---

## Configuration

Everything is environment variables; see `.env.example`. The ones you are most
likely to change:

| Variable | Default | Notes |
|---|---|---|
| `TTS_BACKEND` | `piper` | or `edge` |
| `PIPER_VOICE` | `en_US-hfc_male-medium` | `python -m piper.download_voices` lists all |
| `MAX_SHORT_SECONDS` | `59` | hard cap per part |
| `DAILY_SUBREDDITS` | `relationship_advice,tifu,AmItheAsshole` | for the batch job |
| `MIN_POST_CHARS` / `MAX_POST_CHARS` | `900` / `2300` | batch post filter |

### TTS backends

| | Piper (default) | edge-tts |
|---|---|---|
| Cost | free | free |
| Key required | no | no |
| Network | none, fully offline | yes |
| Quota / rate limit | none | per-IP, undocumented |
| Word timings | interpolated per sentence | exact, from the service |
| Stability | a local ONNX file | undocumented endpoint, can break |

Piper is GPL-3.0 as of `OHF-Voice/piper1-gpl` (the original `rhasspy/piper` went
read-only in Oct 2025 and was MIT). Running it as a library on your own machine
is not distribution, so this does not affect your project's licensing — but know
it before you ship Piper inside anything you hand to someone else.

---

## Tests

```bash
.venv/bin/python -m pytest tests/ -q         # 24 tests, no ffmpeg/network needed
.venv/bin/python scripts/smoke_render.py     # full render, needs ffmpeg + voice
```

The part-splitting tests sweep every caption count from 2 to 90 across three
title lengths, asserting no part exceeds the cap and no part is a stub.

---

## What changed from v1

| Removed | Replaced by | Why |
|---|---|---|
| Selenium + headless Chrome + Reddit password login (~400 lines) | `praw` over the OAuth API | The data is public over an API. No browser, no credentials, no obfuscated CSS class names, no ToS risk. |
| `whisper_timestamped` + PyTorch | nothing | Timings are known at synthesis time. |
| Google Cloud TTS | Piper | Offline, free, no key, no per-character billing. |
| MoviePy + ImageMagick | ffmpeg + libass | One filter instead of a Python object per caption. Also removes a hardcoded `C:\Program Files\ImageMagick` path. |
| pydub + numpy loudness math | ffmpeg `loudnorm` | Same −14 LUFS target, done by the EBU R128 implementation. |
| `demoji` | a codepoint-range regex | No runtime table download. |
| Duplicated `run_N()` / `__main__` blocks, two `login()` copies, two import-time `webdriver.Chrome()` instances | one entrypoint per concern | `run.py` used to spawn two browsers and leak one. |
| `def make_video(...): h` | deleted | It was a bare `h` — an instant `NameError`. |

Rendering a 59-second part takes about 7 seconds.

### Bugs fixed along the way

- Post titles skipped profanity censoring entirely, so they went uncensored into
  the narration, the title card and the output filename.
- `TIFU` expanded to "Today I f***ed up" *after* censoring ran, smuggling the
  word back into the audio.
- The last part could exceed `MAX_SHORT_SECONDS`, making it ineligible as a short.
- Greedy packing produced stub tails (a 58s part followed by a 4s part) instead
  of two balanced halves.
- Whole-word profanity matching missed every inflection (`fucked`, `fucking`),
  while the original's `str.replace` turned `cocktail` into `rodtail`.
