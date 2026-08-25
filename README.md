# Frame Finder

Locates the exact video frame where a given on-screen dialogue first
appears, and extracts the text.

## Quickstart (assignment MVP -- no service/frontend needed)

```bash
pip install -r requirements.txt
cp .env.example .env

python cli.py \
  --url "https://ok.ru/video/248244667877" \
  --text "My mind rebels at stagnation"
```

Output: JSON to stdout + `outputs/<video_id>/<text_hash>/result.json` and
`frame.png`, containing timestamp, frame number, recognized text, and the
extracted frame image.

## How it decides where to look

Two-phase sampling (`core/sampling/`):
1. **Coarse pass** (`coarse_sampler.py`): the whole video is walked at a
   fixed interval (default 1s), running OCR on each sampled frame and
   scoring it against the target dialogue.
2. **ROI refinement** (`roi_sampler.py`): once a coarse hit clears the
   similarity threshold, we step backward in fine increments (default
   0.1s) to find the earliest frame at which the text is already present
   -- this backward walk is what pins down the *first* frame rather than
   just *a* frame where the dialogue is visible.

## How it determines the relevant frame

`core/resolver.py` ties sampling + OCR + matching together: it treats the
earliest timestamp (across the refined backward walk) whose OCR text
clears the similarity threshold as the answer. See
`core/matching/temporal_aggregator.py::earliest_hit`.

## How it extracts text

`core/ocr/engine.py` wraps EasyOCR, whose detector/recognizer pair is a
DBNet-style detector + CRNN-style recognizer -- matching the original
architecture diagram's OCR stage. Detector/recognizer are exposed as
swappable interfaces (`core/ocr/detector.py`, `core/ocr/recognizer.py`) so
a standalone DBNet/CRNN checkpoint can be substituted without touching the
rest of the pipeline.

Frames are preprocessed first (`core/preprocessing/frame_preprocessor.py`):
grayscale, denoise, CLAHE contrast boost, optional crop to a known ROI.

## Handling ambiguity / uncertainty

- Detections are filtered for OCR noise before matching
  (`core/matching/text_filter.py`).
- Text is compared to the target via fuzzy similarity, not exact match
  (`core/matching/similarity.py`, `rapidfuzz.token_sort_ratio`), since OCR
  reads are never pixel-perfect. Threshold is configurable
  (`TEXT_SIMILARITY_THRESHOLD`, default 0.82).
- If the *same* dialogue text reappears later in the video, the first
  chronological occurrence is reported as the answer and the rest are
  returned as `other_matches` rather than silently dropped.
- If nothing clears the similarity threshold, the pipeline returns
  `matched: false` plus the closest candidate it did see
  (`best_near_miss`), so a failure is inspectable rather than silent.

## Running the full stack (service + frontend)

```bash
# 1. backend -- runs with zero infra: falls back to SQLite (no
#    POSTGRES_DSN), an in-memory job store (no Redis), and local-disk
#    frame serving (no MinIO). Set the real env vars in .env to use
#    actual Postgres/Redis/MinIO instead.
pip install -r requirements.txt
uvicorn service.main:app --reload

# 2. frontend
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL, defaults to http://localhost:8000
npm run dev
```

Open the Vite dev URL, paste a video URL, optionally a target dialogue
line, and submit. The UI polls job status, then shows every detected
dialogue line (searchable) plus a highlighted result for the target line
if one was given.

## Full-stack API

```
POST /videos/process            {url, target_text?, force?} -> {job_id, video_id, status}
GET  /videos/{job_id}/status    -> {status: pending|processing|done|error, ...}
GET  /videos/{video_id}/results -> {dialogues: [...], target_matches: [...]}
GET  /videos/{video_id}/search?q=...  -> fuzzy-ranked dialogue matches
```

`service/workers/video_worker.py` runs `core.pipeline.process_video_full()`
(new, alongside the CLI's `process_video()`) on a background thread pool:
it always runs `core/dialogue_scan.py`'s full-video scan for the "display
ALL detected dialogues" feature, and additionally runs the existing
backward-refined `core.resolver.resolve()` when a target line is given, for
a frame-accurate answer on that specific line. Results persist to
Postgres/SQLite (`service/db/`); frames upload to MinIO when configured,
falling back to local disk otherwise (`service/storage/minio_client.py`);
job status lives in Redis, falling back to an in-process store
(`service/cache/redis_client.py`) -- each of these three degrades
gracefully rather than requiring infra just to run the service locally.

## LLM / AI tool usage

This repo (core pipeline, service layer, frontend, and this README) was
built with Claude (Anthropic) as a pair-programming assistant in a single
iterative session: the assignment brief and architecture diagram were
provided as the design brief, `core/` was implemented and validated first
(including an end-to-end run against a synthetic ffmpeg-generated test
video with the OCR backend swapped for the local `tesseract` binary, since
the target environment has no network access to fetch EasyOCR's model
weights), then `service/` and `frontend/` were built on top of the
validated `core/` pipeline, reusing its modules rather than duplicating
OCR/matching/sampling logic in the service layer. All service-layer
external dependencies (Redis, Postgres, MinIO) were given explicit
graceful-degradation fallbacks so the full stack is runnable for local
review without provisioning that infra first, and that fallback behavior
was itself executed and checked, not just written. Frontend files were
syntax/import validated with `esbuild` (bundling `src/main.jsx`'s full
import graph) since `npm install` requires network access unavailable in
this environment.

## Design rationale: why this stack

The full stack (React frontend, FastAPI, Redis, PostgreSQL, MinIO) supports
a multi-video, searchable-history product. The assignment itself is
single-URL, single-dialogue extraction, so `core/` is a self-contained
pipeline runnable via `cli.py` with zero infra dependencies -- see
`core/pipeline.py`, which also does its own lightweight flat-file result
caching (keyed by video URL + target text) independent of the service
layer's Redis/Postgres cache. `service/` and `frontend/` build on top of
that validated `core/` pipeline: `service/workers/video_worker.py` and
`core/pipeline.py::process_video_full()` are the only new orchestration
code the full stack needed -- everything below that (sampling, OCR,
matching, resolving) is reused unchanged from `core/`.

## Folder structure

```
frame-finder/
├── core/                  # pure pipeline, runnable standalone
│   ├── config.py
│   ├── source/            # URL -> local file, ffprobe metadata
│   ├── sampling/          # coarse + ROI-refine timestamp strategies
│   ├── extraction/        # ffmpeg frame grabs
│   ├── preprocessing/     # OpenCV cleanup before OCR
│   ├── ocr/                # detector/recognizer interfaces + EasyOCR engine
│   ├── matching/          # fuzzy similarity, noise filtering, temporal aggregation
│   ├── resolver.py        # single target -> frame-accurate first appearance
│   ├── dialogue_scan.py   # full video -> every distinct dialogue line
│   └── pipeline.py        # orchestrates the above; CLI and service entrypoints
├── cli.py                 # MVP entrypoint (single URL + target, no infra)
├── service/                # FastAPI + Redis + Postgres + MinIO, each with a
│   ├── main.py             # graceful local-dev fallback if infra is absent
│   ├── routers/            # /videos/process, /status, /results, /search
│   ├── workers/            # background job runner -> core.pipeline
│   ├── db/                 # SQLAlchemy models + session (SQLite fallback)
│   ├── cache/              # Redis job-status client (in-memory fallback)
│   └── storage/            # MinIO frame storage client (local-disk fallback)
├── frontend/               # React + Vite + Tailwind UI
│   └── src/
│       ├── api/client.js
│       └── components/     # form, status, timeline, search, dialogue list, frame modal
├── outputs/                 # local run artifacts (result.json + frame.png per run)
└── tests/
```

## Status

- [x] Folder structure scaffolded
- [x] core/ pipeline modules written (config, source, sampling, extraction,
      preprocessing, ocr, matching, resolver, dialogue_scan, pipeline, cli)
- [x] Validated end-to-end: synthetic ffmpeg test video + tesseract-backed
      OCR stand-in (no network access to EasyOCR's weights in this
      environment) exercised dialogue_scan, resolver's backward refinement,
      and pipeline.process_video_full() -- see the "LLM / AI tool usage"
      section for what that verification did and didn't cover
- [x] service/ layer implemented: routers wired to a background worker,
      Postgres/SQLite persistence, Redis job status, MinIO frame storage
- [x] frontend/ implemented: submission form, live status, target-match
      hero card, dialogue timeline, search/filter, frame lightbox
- [x] Prompts-used documentation filled in above
- [ ] Not run against a real network video URL or real
      Redis/Postgres/MinIO/EasyOCR in this environment (no network egress
      here) -- run `cli.py` against the sample ok.ru URL, and the full
      stack with real infra, before treating this as production-verified
