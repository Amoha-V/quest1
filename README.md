# Frame Finder

Given a video URL and a target line of dialogue, find the exact frame where
it first appears - whether that line is shown as on-screen/burned-in text or
only ever spoken - and return the timestamp, frame number, recognized text,
and the frame image itself.

- **`DESIGN.md`** - technical architecture, optimizations (with measured
  numbers), edge cases.
- **`approach.md`** - how the problem was broken down and reasoned through.

## Prerequisites

- Python 3.12 (tested on 3.12.6)
- Node.js 18+ (tested on 22.16.0) + npm, if you want the frontend
- Docker Desktop, for Postgres/Redis/MinIO (the service layer only - see
  [Running just the CLI](#running-just-the-cli) if you want to skip this
  entirely)
- ffmpeg - you don't need to install this yourself; `static-ffmpeg` (a
  Python dependency) downloads and caches a static binary on first use

## Setup

```powershell
git clone <this-repo-url>
cd frame-finder

# --- Python environment ---
python -m venv venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& .\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# --- Configuration ---
cp .env.example .env
# .env works as-is against the docker-compose services below. Adjust
# COARSE_SAMPLE_INTERVAL_SEC / ASR_MODEL_SIZE / ASR_CHUNK_WORKERS if your
# machine has very different CPU/RAM than a typical dev laptop -- see
# DESIGN.md's "Known limitations" section on why these aren't auto-tuned.

# --- Backing services (Postgres, Redis, MinIO) ---
docker compose up -d
```

First run of anything OCR- or ASR-related will also download model weights
(EasyOCR's detector/recognizer, and the `faster-whisper` model set by
`ASR_MODEL_SIZE`) - expect a one-time delay for that, cached afterward.

## Running

### Standalone CLI (no Docker, no frontend - the minimal path)

This is the direct assignment-shape entrypoint: one URL in, one answer out.
It does **not** need the Docker services above - only `core/`'s file-based
caching is used.

```powershell
python cli.py --url "https://ok.ru/video/248244667877" --text "My mind rebels at stagnation"
```

Add `--force` to bypass the cached result and reprocess.

### Full service (FastAPI backend + React frontend)

Needs the Docker services running (`docker compose up -d`) first.

```powershell
# backend, in one terminal
python run.py
# -> http://127.0.0.1:8000  (docs at /docs, health check at /health)

# frontend, in another terminal
cd frontend
npm install   # first time only
npm run dev
# -> http://localhost:5173
```

Submitting the same URL + target text again returns the cached result
instantly rather than reprocessing - see `DESIGN.md`'s Caching section.

## Running tests

```powershell
python -m pytest tests/ -q
```

`tests/test_job_cache.py` needs a live Postgres connection (`docker compose
up -d` first); the rest run standalone.

## Configuration reference

All of the following are read from `.env` (see `.env.example` for the full,
commented list of defaults) via `core/config.py`:

| Area | Key variables |
|---|---|
| Sampling | `COARSE_SAMPLE_INTERVAL_SEC`, `CHANGE_DETECTION_ENABLED` |
| OCR / matching | `OCR_MIN_CONFIDENCE`, `TEXT_SIMILARITY_THRESHOLD`, `SUBTITLE_ROI_*` |
| ASR | `ASR_MODEL_SIZE`, `ASR_CHUNK_WORKERS`, `ASR_LANGUAGE`, `ASR_VAD_FILTER` |
| Service layer | `REDIS_URL`, `POSTGRES_DSN`, `MINIO_*` |

## Project layout

```
cli.py                  standalone single-shot entrypoint
run.py                   FastAPI service entrypoint
core/                     the actual detection pipeline
  resolver.py, dialogue_scan.py     OCR (on-screen text) path
  asr/                               ASR (spoken dialogue) path
  combined_resolver.py              runs both concurrently, merges results
  ocr/, extraction/, sampling/, matching/, preprocessing/   supporting stages
service/                  FastAPI app, Postgres/Redis/MinIO integration
frontend/                 React UI
tests/                    pytest suite
DESIGN.md, approach.md    documentation
```

## Troubleshooting

- **Postgres/MinIO/Redis connection errors**: confirm the containers are up
  (`docker compose ps`) and match the ports in `.env`.
- **Very slow first run**: expected - model downloads (EasyOCR, Whisper) and
  a full OCR+ASR pass on a long video happen once; subsequent runs against
  the same video hit the caches described in `DESIGN.md`.
- **Backend seems stuck mid-scan after you edit a file**: `run.py` runs
  uvicorn with `reload=True`; editing source files while a job is in flight
  can kill it silently (a real issue hit during development - see
  `DESIGN.md`'s "Real failures hit and fixed"). Avoid editing while a scan
  is running, or restart the server after.
