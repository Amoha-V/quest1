# Frame Finder - Design & Approach

## Problem

Given a video URL, find the exact frame + timestamp where a target line of dialogue
first appears, extract the frame image and the recognized text, without requiring
manual inspection of the video. Must work whether the dialogue is shown as
on-screen/burned-in text **or** only ever spoken.

## Why two detection modalities

The assignment's own sample video (`https://ok.ru/video/248244667877`, target line
*"My mind rebels at stagnation"*) turned out to have **no burned-in captions at
all** - the line is only ever spoken. An OCR-only design can never succeed on a
video like that, no matter how long or how cleverly it scans. So the system runs
two independent detectors and merges their results, rather than assuming one
modality upfront:

- **OCR** - on-screen text (`core/resolver.py`, `core/dialogue_scan.py`)
- **ASR** - spoken dialogue, speech-to-text (`core/asr/`)

merged by **`core/combined_resolver.py`**.

## High-level layout

```
cli.py                  standalone single-shot entrypoint (assignment MVP,
                         no service/frontend dependency)
run.py, service/        FastAPI service + Postgres/Redis/MinIO-backed
                         multi-video product layer, React frontend in frontend/
core/                   the actual detection pipeline -- used by both of the
                         above, neither re-implements pipeline logic
```

## OCR path - "where does it look, on screen?"

1. **Coarse sampling** (`core/sampling/coarse_sampler.py`) - walk the video at a
   fixed interval (default 1.0s in code, tuned to 3.0s in `.env` for this
   project - see Optimizations). `core/extraction/frame_stream.py` decodes this
   with a **single ffmpeg process** using `select=not(mod(n,K))` instead of
   spawning a fresh ffmpeg process + reseek for every timestamp.
2. **Spatial ROI** (`core/sampling/roi_sampler.py::subtitle_band`) - crop to the
   lower 30% of the frame before OCR, so watermarks/titles elsewhere on screen
   are ignored.
3. **Preprocessing** (`core/preprocessing/frame_preprocessor.py`) - denoise
   (`fastNlMeansDenoising`) + CLAHE contrast boost on the cropped band.
4. **Detection + recognition** (`core/ocr/engine.py`) - EasyOCR (DBNet detector +
   CRNN recognizer), CPU-only. Calls `detect()` first and only pays for the
   (much pricier) `recognize()` pass when the detector actually found a region -
   this only works correctly by calling `detect()` then `recognize()` directly
   (not `detect()` then `readtext()`, which silently re-runs its own internal
   detection pass - a real regression caught and fixed this session).
5. **Fuzzy match** (`core/matching/similarity.py`) - `rapidfuzz.fuzz.token_sort_ratio`
   against the target text, accepted at `text_similarity_threshold` (default 0.82).
6. **Parallelization** (`core/ocr/parallel_scan.py`) - coarse ticks are OCR'd in
   chronological batches across a process pool (`default_worker_count()` =
   `min(cpu_count-1, 8)`), preserving "first chronological match" correctness:
   a batch is only reported once every frame in it (and everything before it)
   has been checked, so `stop_at_first` still behaves as if sequential.
7. **Backward refine** (`core/resolver.py`, using `roi_sampler.refine_timestamps_before`)
   - once a coarse hit is found, step backward in 0.1s increments to find the
   earliest frame the text is still present on. This is the actual "first
   frame" reported, not the coarse tick that happened to trigger the hit.

## ASR path - "where does it look, in the audio?"

1. **Audio extraction** (`core/asr/audio_extractor.py`) - ffmpeg, 16kHz mono
   WAV, cached per `video_id`.
2. **Chunked parallel transcription** (`core/asr/parallel_transcriber.py`) -
   splits the audio into `asr_chunk_workers` pieces (default 2, with a 5s
   overlap so a line spanning a chunk boundary isn't lost), transcribes each
   concurrently in its own process using `faster-whisper` (`base.en`, int8,
   CTranslate2), then merges segments back with real (global) timestamps.
3. **Caching** (`core/asr/transcriber.py`) - the merged transcript is written
   to `outputs/<video_id>/transcript.json`; later resolves against the same
   video reuse it instantly instead of re-transcribing.
4. **Sliding-window fuzzy match** (`core/asr/resolver.py`) - Whisper segments
   are clause-length, so a target phrase won't always land on exactly one
   segment. Concatenates up to 4 consecutive segments per window and scores
   each with the *same* `similarity_score()` OCR uses, keeping the
   best-scoring window's start timestamp as the onset.

## Combined resolution (`core/combined_resolver.py`)

- Runs `resolve()` (OCR) and `resolve_audio()` (ASR) **concurrently** via a
  2-worker `ThreadPoolExecutor` (each side releases the GIL into its own
  process pool / native inference code, so plain threads are enough).
- **Merge rule**, matching "the dialogue that *first* appears": if both match,
  earlier timestamp wins. If only one matches, use it. If neither matches,
  report whichever had the higher-similarity near-miss - the failure mode
  stays inspectable, never a silent blank.
- **Short-circuit cancellation**: a `threading.Event` per side. As soon as one
  side returns a confident match, the other's event is set. OCR's coarse loop
  checks it once per tick; ASR checks it once before starting (it's a single
  one-shot batch, not a steppable loop). This matters concretely for this
  project's actual video: since it has no captions, OCR's scan would otherwise
  never stop early and would burn through the whole ~54-minute video for
  nothing, even though ASR already had the answer in seconds from cache.
  Verified end-to-end (see Optimizations).
- **Robustness**: both sides are wrapped in try/except. A crash in one
  modality (`BrokenProcessPool`, observed under real memory pressure - see
  Optimizations) is treated as "no match" for that side rather than taking
  down a result the other side found fine.

## Caching - five independent layers

Caching is arguably the single biggest optimization in this system: every
layer below turns "redo expensive work" into "return an already-known
answer," and they compose (a fully-cached repeat request skips the pipeline
entirely, not just runs it faster). Each layer is keyed and scoped
independently:

| Layer | Where | Keyed by | Skips |
|---|---|---|---|
| Video download | `core/source/downloader.py` | `video_id` (hash of URL) | re-downloading the source video (can be 1GB+) |
| Audio extraction | `core/asr/audio_extractor.py` | `video_id` | re-running ffmpeg audio extraction |
| ASR transcript | `core/asr/transcriber.py` → `outputs/<video_id>/transcript.json` | `video_id` | re-transcribing the full audio (the expensive ASR step - this is what turns a ~5-6min chunked transcription into a near-instant fuzzy-match pass on every subsequent query against the same video) |
| Pipeline result (file) | `core/pipeline.py` - `result.json` (CLI, keyed by `video_id` + sha1(target_text)) and `manifest_first.json` / `manifest_all.json` (service) | `video_id` (+ target text where relevant) | re-running OCR+ASR entirely for an identical repeat query |
| Service job state | `service/db/session.py` (Postgres `videos`/`dialogues` tables) + `service/cache/redis_client.py` (Redis, 7-day TTL) | `video_id` + query hash (`job_id`) | the *entire* pipeline call - a repeat request for the same (video, target text) returns `"Cache hit (postgres) - skipped pipeline"` directly from the API layer, before `core.pipeline` is even invoked |

Verified end-to-end this session (see the "is the cache layer still
available?" check): after one successful run, every layer was independently
confirmed populated and correct - downloaded video + audio on disk, transcript
JSON cached, Postgres `videos.status = "done"` with the matching `dialogues`
row, Redis holding both job status and result with TTL intact, and the
extracted frame present in MinIO. A repeat submission of the same URL +
target text is expected to return instantly via the Postgres/Redis layer
alone, without touching OCR, ASR, or ffmpeg at all.

Cache invalidation is intentionally simple and manual: pass `force=True`
(CLI `--force`, or the service's equivalent) to bypass the file/DB caches and
reprocess. There's no automatic invalidation (e.g. on video content change at
the same URL) - a reasonable trade-off for this project's scope, not a
production-grade cache-coherence design.

## How the exact frame/timestamp is determined

- OCR: the coarse hit's timestamp, corrected by backward refine to the actual
  onset (earliest frame the text is present on).
- ASR: the matched transcript window's `start_sec` - the moment the speaker
  begins that line.
- Either way: `frame_number = round(timestamp_sec * fps)`
  (`VideoMetadata.timestamp_to_frame`), and `core/extraction/frame_extractor.py`
  pulls that exact frame via `ffmpeg -ss <ts> -i <video>` (seek before input,
  for fast keyframe-adjacent accuracy), saved as a PNG.

## Handling ambiguous / uncertain results

- Both modalities score against `text_similarity_threshold` (0.82) - below
  that, `matched=False` with `best_near_miss` populated (the closest candidate
  actually seen), never a silent failure.
- `ResolveResult.source` (`"ocr"` or `"asr"`) records which modality actually
  answered, for transparency/debugging.
- `resolve()` supports `stop_at_first=False` (and reports `other_matches`) for
  the case where a line appears more than once - built and tested, not
  currently wired to any UI/CLI flag, kept as a documented extensibility point
  given the assignment explicitly says the requirement may change in the
  interview (e.g. "show every occurrence, not just the first").
- Every result - OCR or ASR, matched or not - is written to Postgres, Redis,
  and a flat JSON file, so a low-confidence or failed run is always
  inspectable after the fact, not just a spinner that goes nowhere.

## Optimizations

All measured against the actual assignment video (`ok.ru/video/248244667877`,
3261.8s ≈ 78,205 total frames, 960x720, 23.976fps) on the dev machine (12
logical cores, 16GB RAM, ~3-4GB typically free with Docker/IDE already
running).

### Foundational (baseline architecture, not a mid-session change)

These are optimizations in the sense that they're deliberate algorithmic
choices avoiding brute-force work - they were part of the design from the
start, not something bolted on mid-session, but they're the ones with the
single largest impact and are worth stating explicitly rather than leaving
implicit in the architecture description above.

| Choice | What it avoids | Scale |
|---|---|---|
| **Coarse (interval) sampling** instead of OCR'ing every decoded frame (`coarse_sampler.py`) | OCR'ing all 78,205 frames of the video | at the current 3.0s interval: **1,087 ticks - a 71.9x reduction** vs frame-by-frame (24x even at the original 1.0s default) |
| **Spatial ROI crop** to the subtitle band before OCR (`roi_sampler.py::subtitle_band`) | Running detection/recognition over the full frame, including regions dialogue never appears in | 960x720 → 960x216 = **3.33x fewer pixels** OCR'd per frame |
| **`stop_at_first`** - the coarse loop breaks the moment a match clears threshold (`resolver.py`) | Scanning the remainder of the video after the answer is already known | turns an O(n) scan into O(match position) in the common case where the line isn't near the very end |
| **Bounded backward refine** (`roi_sampler.py::refine_timestamps_before`) - fine-grained 0.1s stepping only within a small window around one coarse hit | Fine-stepping the *entire* video at 0.1s resolution (a ~30x finer walk) to get onset-frame precision | refine work is O(refine_window / refine_step) ≈ 10 extra frames, not O(video_duration / 0.1s) ≈ 32,618 |
| **VAD filtering** in ASR (`faster-whisper`'s `vad_filter=True`) | Running the transcription model over silent/non-speech audio regions | skips compute proportional to however much of the track has no speech |

### Mid-session changes (chronological, with measured numbers)

| # | Change | Measured effect |
|---|---|---|
| 1 | Coarse interval 1.0s → 3.0s | ~3x fewer OCR calls (on top of the 24x the interval-sampling design already provides - see above) |
| 2 | Single-process ffmpeg streaming decode (`frame_stream.py`) instead of one ffmpeg spawn+seek per timestamp | ffmpeg extraction: 0.096s/frame → 0.017s/frame; verified pixel-identical output |
| 3 | `detect()` → `recognize()` directly (skip recognition on 0-detection frames) instead of `detect()` → `readtext()` (which silently doubled detection cost) | fixed a real regression found while implementing #4 |
| 4 | 8-way process-pool parallel OCR (`ocr/parallel_scan.py`), chronological batching preserves "first match" correctness | - |
| 5 | Fixed severe thread oversubscription: each OCR worker was running ~35 threads instead of 1 (`torch.set_num_threads(1)` alone doesn't constrain OpenMP/MKL/OpenCV, which size themselves at import time) - fixed by setting `OMP_NUM_THREADS` etc. *before* importing torch/cv2 in each worker | throughput was ~8.6x below the naive 8x-parallel expectation before this fix |
| 6 | ASR model `small.en` → `base.en` | full-video transcription: ~955s → ~334s |
| 7 | Chunked parallel ASR transcription (`asr/parallel_transcriber.py`), 4 workers → reduced to 2 after a real `BrokenProcessPool` memory crash | further speedup on top of #6, at a safe memory footprint for this machine |
| 8 | Cross-modality cancellation (see Combined resolution) | worst-case combined-resolve time: ~8-10min (OCR scanning to exhaustion) → **40.16s** (dominated entirely by one-time EasyOCR model load), once ASR confidently answers from cache |
| 9 | Five-layer caching (see Caching) - download / audio / transcript / pipeline-result / service job state | a fully-cached repeat request for the same (video, target text) skips OCR, ASR, and ffmpeg entirely and returns from Postgres/Redis directly - the largest possible speedup (no pipeline work at all) for the repeat-query case the UI explicitly supports ("submitting the same URL and dialogue again loads the cached result") |

Net effect on this project's actual video: the original design never
completed in 90+ minutes across several attempts (compounded by unrelated
infra issues below). The final, verified pipeline resolves the same video in
**under a minute**, correctly, at 93.1% similarity.

## Edge cases

| Edge case | Handling | Status |
|---|---|---|
| Dialogue is spoken, not captioned | ASR path (`core/asr/`) | Solved - this is literally the assignment's real video |
| OCR noise / misreads | `rapidfuzz` fuzzy match, same scorer used for ASR misrecognition | Solved |
| VFR video | Frame extraction seeks by wall-clock timestamp (ffmpeg `-ss`), correct regardless of frame rate variability | Mostly solved - the *reported* `frame_number` (`ts * average_fps`) can drift slightly on true VFR content; the seek/match mechanism itself is unaffected |
| Low quality video | Denoise + CLAHE contrast before OCR | Partial - helps compression noise/low contrast, not resolution/motion blur |
| Short-lived on-screen text (shorter than the coarse interval) | Optional `change_detector.py` - a fine-interval (0.15s), OCR-free pixel-diff pre-pass that flags candidate timestamps for the coarse OCR loop to also check | Partial - off by default (`CHANGE_DETECTION_ENABLED=false`); real but adds cost |
| Text on clothes/logos vs. real dialogue | Spatial ROI (lower-third crop) | Partial - no temporal-persistence requirement, a one-frame hit in-band still counts |
| Multiple text regions in one frame | bbox stored on every promoted hit | Partial - only the single best-scoring region per frame is kept, others discarded |
| Duplicate/near-identical frames | - | Not implemented - no perceptual-hash frame dedup exists |
| Repeated dialogue (same line, later in the video) | `other_matches` / `stop_at_first=False` | Partial - built, not wired to any UI/CLI flag |
| Neither modality confident | Reports the higher-similarity near-miss from either side | Solved - never a silent failure |
| Video has no subtitle track *and* no clear speech (e.g. music only) | Both `matched=False`, near-miss reported | Solved - handled gracefully, not "stuck" |

## Real failures hit and fixed this session (useful context for defending the design)

1. **`uvicorn --reload` silently killing in-flight jobs.** Editing source
   files while a job was running triggered an auto-restart that killed the
   task mid-scan without ever writing an error status - Redis just showed a
   permanently frozen "processing" state. No code fix (this is a dev-server
   behavior, not a pipeline bug) - mitigated by not editing files while jobs
   are in flight, and by clearing stale job entries on restart.
2. **OCR/ASR concurrent memory pressure → `BrokenProcessPool`.** Loading
   multiple EasyOCR + Whisper model instances at once on a memory-constrained
   machine (~3-4GB free out of 16GB) crashed a worker process outright (a Rust
   allocator failure). Fixed by (a) catching the crash per-modality in
   `combined_resolver.py` instead of letting it take down the whole result,
   and (b) lowering `ASR_CHUNK_WORKERS` to a safer default.
3. **A stuck reloader.** A file edit triggered "Reloading..." but the restart
   never completed while 8 OCR worker processes were still holding resources
   - the old process kept serving requests on stale code indefinitely.
   Diagnosed via the log (a "Reloading..." with no matching "Started server
   process" afterward) and fixed by killing the whole process tree and
   starting clean.
4. **OCR double-detection regression.** An earlier version of the
   detect-then-skip-recognition optimization called `detect()` and then
   `readtext()` - but `readtext()` re-runs detection internally, silently
   doubling cost on every frame with any text. Caught by profiling against
   the real video, fixed by calling `detect()` → `recognize()` directly
   (mirroring EasyOCR's own internal `readtext()` implementation).

## Known limitations / explicitly deferred

- The OCR (8 workers) / ASR (2-4 workers) core split is a **static** budget
  tuned empirically for this specific dev machine's actual headroom, not
  dynamically detected from available RAM/CPU at runtime.
- Soft (embedded, non-burned-in) subtitle tracks aren't checked for - `ffprobe`
  confirmed the assignment video has none, so this wasn't built, but it would
  be a strictly cheaper, more authoritative signal than either OCR or ASR when
  present.
- No perceptual-hash duplicate-frame detection, no temporal-persistence
  requirement for OCR hits (see Edge cases table).
- `stop_at_first=False` / multi-occurrence reporting is implemented but not
  exposed through the CLI or API.
