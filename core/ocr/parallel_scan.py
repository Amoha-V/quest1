"""
Process-pool parallelization of the coarse OCR scan.

Profiling against a real video (960x720) showed OCR dominates the coarse
loop's wall-clock time: ~1.6-3s+ per frame for detect+recognize on CPU,
vs ~0.02s for frame decode (frame_stream.py's single-process ffmpeg stream)
and ~0.1s for preprocessing. Frame decode stays sequential in the main
process -- it's already cheap and strictly ordered. OCR is the >90%-of-cost
part worth spending multiple CPU cores on.

Correctness constraint: resolver.py / dialogue_scan.py need the *first
chronological* match (stop_at_first), so results can't be consumed in
whatever order workers happen to finish. This dispatches CHRONOLOGICAL
BATCHES of `max_workers` frames at a time via ProcessPoolExecutor.map(),
which blocks until the whole batch is done but yields results in submission
(== timestamp) order regardless of which worker finished first. Nothing in
an unprocessed batch could contain an earlier match than something already
yielded from a prior batch, so callers can `break` on the first match
exactly as if this were a strictly sequential scan -- just computed
`max_workers`-wide at a time.

Each worker process loads its own EasyOCR reader once (on first task) and
pins itself to a single torch thread (_init_worker) so N worker processes
running concurrently don't oversubscribe the CPU by each also fanning out
torch's own intra-op parallelism.
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

import numpy as np

from core.config import settings
from core.extraction.frame_stream import stream_coarse_frames
from core.ocr.types import OcrDetection
from core.source.metadata import VideoMetadata

logger = logging.getLogger(__name__)


def default_worker_count() -> int:
    cpu = os.cpu_count() or 2
    return max(1, min(cpu - 1, 8))


def _init_worker() -> None:
    """
    Pin this worker to a single thread before anything BLAS/OpenMP-backed
    gets imported. torch.set_num_threads(1) alone is not enough -- it only
    controls torch's own intra-op pool. numpy/torch's underlying MKL/OpenMP
    backend and OpenCV's own thread pool each size themselves independently
    at import time from OMP_NUM_THREADS/etc (or os.cpu_count() if unset), so
    setting torch.set_num_threads() *after* those libraries already
    initialized does nothing for them. Measured on this project: without
    this fix, each of 8 worker processes was still running ~35 threads
    (8 workers x ~35 threads competing for 12 logical cores), which
    swallowed almost the entire benefit of process-level parallelism.
    """
    for var in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        os.environ[var] = "1"

    try:
        import cv2

        cv2.setNumThreads(1)
    except Exception:  # pragma: no cover - opencv always present in this project
        pass
    try:
        import torch

        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)  # separate pool from set_num_threads()
    except Exception:  # pragma: no cover - torch always present in this project
        pass
    from core.ocr.engine import _get_reader

    _get_reader()  # load DBNet+CRNN once per worker process, reused across tasks


def _ocr_task(payload: Tuple[float, np.ndarray]) -> Tuple[float, List[OcrDetection]]:
    ts, frame = payload
    from core.ocr.engine import run_dialogue_ocr

    return ts, run_dialogue_ocr(frame)


def parallel_coarse_scan(
    video_path: Path,
    meta: VideoMetadata,
    interval_sec: float,
    max_workers: Optional[int] = None,
) -> Iterator[Tuple[float, List[OcrDetection]]]:
    """
    Yield (timestamp, detections) in chronological order, OCR'd across a
    pool of worker processes `max_workers` frames at a time.

    Stopping iteration early (breaking the consuming for-loop) leaves
    unsubmitted frames simply never decoded/OCR'd (stream_coarse_frames is
    pulled lazily, batch by batch) -- wrap consumption in
    contextlib.closing(...) so `break` promptly tears down the ffmpeg
    process feeding this generator, same as iter_scan_frames().
    """
    workers = max_workers or default_worker_count()
    logger.info("Parallel coarse scan: %d worker process(es)", workers)

    frame_iter = stream_coarse_frames(video_path, meta, interval_sec)
    try:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as pool:
            batch: List[Tuple[float, np.ndarray]] = []
            for ts, frame in frame_iter:
                batch.append((ts, frame))
                if len(batch) >= workers:
                    yield from pool.map(_ocr_task, batch)
                    batch = []
            if batch:
                yield from pool.map(_ocr_task, batch)
    finally:
        frame_iter.close()


def iter_scan_detections(
    video_path: Path, meta: VideoMetadata, on_progress=None
) -> Iterator[Tuple[float, List[OcrDetection]]]:
    """
    (timestamp, detections) pairs for a coarse/dialogue scan loop -- the
    single seam resolver.py / dialogue_scan.py use to get OCR results for
    their walk.

    Uses parallel_coarse_scan() (OCR spread across a worker-process pool)
    when settings.change_detection_enabled is off -- the default, and the
    only case parallel_coarse_scan / stream_coarse_frames support (both
    require a uniform-interval walk, see their docstrings). Falls back to
    sequential per-timestamp OCR over merged_sampler's irregular timestamp
    union when change detection is on, since that can't be expressed as the
    single ffmpeg select filter stream_coarse_frames relies on.

    Wrap consumption in contextlib.closing(...) so an early `break`
    (stop_at_first) promptly tears down the worker pool and ffmpeg process
    instead of continuing to decode/OCR the rest of the video.
    """
    if not settings.change_detection_enabled:
        yield from parallel_coarse_scan(video_path, meta, settings.coarse_sample_interval_sec)
        return

    from core.extraction.frame_stream import iter_scan_frames
    from core.ocr.engine import run_dialogue_ocr

    for ts, frame in iter_scan_frames(video_path, meta, on_progress=on_progress):
        yield ts, run_dialogue_ocr(frame)
