"""
Chunked, process-parallel transcription: splits the audio into N segments
(with a small overlap so dialogue spanning a chunk boundary isn't lost),
transcribes each concurrently in its own process (its own WhisperModel
instance, pinned to a single thread), then merges results back into one
chronological segment list with real (global) timestamps.

Trades faster-whisper's own intra-model thread parallelism (one big model
instance, several threads) for inter-chunk process parallelism (several
small single-threaded model instances): CTranslate2 inference has
diminishing returns much past 2-4 threads for one stream, so splitting the
*work* instead scales more cleanly -- same reasoning as
core/ocr/parallel_scan.py's process-pool approach to OCR, and the same
per-worker thread-pinning fix (see that module's _init_worker docstring for
why OMP_NUM_THREADS etc must be set before torch/ctranslate2 import, not
after).
"""
from __future__ import annotations

import logging
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import List, Tuple

from core.asr.types import TranscriptSegment
from core.config import settings

logger = logging.getLogger(__name__)

_OVERLAP_SEC = 5.0


def _init_worker() -> None:
    for var in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        os.environ[var] = "1"


def _chunk_bounds(duration_sec: float, n_chunks: int) -> List[Tuple[float, float]]:
    n_chunks = max(1, n_chunks)
    step = duration_sec / n_chunks
    bounds = []
    for i in range(n_chunks):
        start = max(0.0, i * step - (_OVERLAP_SEC if i > 0 else 0.0))
        end = min(duration_sec, (i + 1) * step + _OVERLAP_SEC)
        bounds.append((start, end))
    return bounds


def _extract_chunk(audio_path: Path, start: float, end: float, out_path: Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(audio_path),
        "-ss", f"{start:.3f}",
        "-to", f"{end:.3f}",
        "-ac", "1", "-ar", "16000",
        "-f", "wav", "-loglevel", "error",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def _transcribe_chunk(payload: Tuple[str, float]) -> List[dict]:
    chunk_path, offset = payload
    from faster_whisper import WhisperModel

    model = WhisperModel(
        settings.asr_model_size, device="cpu", compute_type="int8", cpu_threads=1
    )
    segments, _ = model.transcribe(
        chunk_path,
        language=settings.asr_language or None,
        vad_filter=settings.asr_vad_filter,
    )
    return [
        {
            "text": seg.text.strip(),
            "start_sec": seg.start + offset,
            "end_sec": seg.end + offset,
            "avg_logprob": seg.avg_logprob,
        }
        for seg in segments
    ]


def transcribe_parallel(
    audio_path: Path, duration_sec: float, work_dir: Path
) -> List[TranscriptSegment]:
    n_chunks = settings.asr_chunk_workers
    bounds = _chunk_bounds(duration_sec, n_chunks)

    work_dir.mkdir(parents=True, exist_ok=True)
    chunk_paths: List[Tuple[str, float]] = []
    for i, (start, end) in enumerate(bounds):
        chunk_path = work_dir / f"chunk_{i:02d}.wav"
        _extract_chunk(audio_path, start, end, chunk_path)
        chunk_paths.append((str(chunk_path), start))

    logger.info(
        "Transcribing %d chunk(s) of ~%.0fs each across %d worker process(es)",
        len(chunk_paths), duration_sec / n_chunks, n_chunks,
    )
    try:
        all_segments: List[TranscriptSegment] = []
        with ProcessPoolExecutor(max_workers=n_chunks, initializer=_init_worker) as pool:
            for result in pool.map(_transcribe_chunk, chunk_paths):
                all_segments.extend(TranscriptSegment(**d) for d in result)

        all_segments.sort(key=lambda s: s.start_sec)
        return all_segments
    finally:
        # Always clean up chunk files, including on a worker crash
        # (BrokenProcessPool) -- these are multi-MB WAV files, not worth
        # leaving behind on failure.
        for chunk_path, _ in chunk_paths:
            Path(chunk_path).unlink(missing_ok=True)
