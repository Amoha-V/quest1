"""
Runs the OCR-based (on-screen text) and ASR-based (spoken dialogue)
resolvers concurrently and merges their results, since target_text could
appear either as on-screen dialogue or as spoken audio (or, in principle,
both). This project's actual assignment video turned out to have no
burned-in captions at all -- spoken-only -- which is what motivated this
module: core.resolver alone can never succeed on such a video, no matter
how long it scans.

Merge rule: "the dialogue that first appears" (same convention as
core.resolver / core.dialogue_scan) -- if both modalities find a confident
match, the earlier timestamp wins. If only one matches, use it. If neither
matches, report whichever had the higher-similarity near-miss, so the
failure mode stays inspectable instead of picking one arbitrarily.

Short-circuit: as soon as either side returns a confident match, the other
side's cancel_event is set so it stops early rather than running to
completion for an answer that can no longer change the outcome. This
matters in one direction specifically -- OCR's coarse scan has no early
stop when the video has no on-screen captions at all (this project's
actual video), so without cancellation a confident ASR match (often
near-instant once its transcript is cached) would still sit blocked behind
several more minutes of a doomed OCR scan for no reason.

CPU/memory budget note: the OCR path spins up its own worker-process pool
(core.ocr.parallel_scan, default cpu_count-1 capped at 8) and ASR spins up
its own chunk-worker pool (core.asr.parallel_transcriber, default
settings.asr_chunk_workers) -- run concurrently via the plain
ThreadPoolExecutor below (each side releases the GIL into its own process
pool / native inference code, so Python-level threads are enough to run
them concurrently). On a memory-constrained machine, 8 OCR workers +
several ASR model-loading workers running at once can exceed available
RAM -- each side's process pool crashing is a real, observed failure mode
(BrokenProcessPool), not hypothetical, so both sides are caught below
rather than let a crash in one modality take down a result the other
modality may have found fine.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from core.asr.resolver import resolve_audio
from core.resolver import ResolveResult, resolve
from core.source.metadata import VideoMetadata

logger = logging.getLogger(__name__)


def _safe_ocr(video_path, meta, target_text, on_progress, cancel_event) -> ResolveResult:
    try:
        return resolve(
            video_path, meta, target_text,
            stop_at_first=True, on_progress=on_progress, cancel_event=cancel_event,
        )
    except Exception:
        logger.exception("OCR resolve() failed -- treating as no match")
        return ResolveResult(matched=False, target_text=target_text, source="ocr")


def _safe_asr(video_path, meta, video_id, target_text, cancel_event) -> ResolveResult:
    try:
        return resolve_audio(video_path, meta, video_id, target_text, cancel_event=cancel_event)
    except Exception:
        logger.exception("ASR resolve_audio() failed -- treating as no match")
        return ResolveResult(matched=False, target_text=target_text, source="asr")


def resolve_combined(
    video_path: Path,
    meta: VideoMetadata,
    video_id: str,
    target_text: str,
    on_progress=None,
) -> ResolveResult:
    ocr_cancel = threading.Event()
    asr_cancel = threading.Event()

    with ThreadPoolExecutor(max_workers=2) as pool:
        ocr_future = pool.submit(_safe_ocr, video_path, meta, target_text, on_progress, ocr_cancel)
        asr_future = pool.submit(_safe_asr, video_path, meta, video_id, target_text, asr_cancel)
        cancel_of = {ocr_future: ocr_cancel, asr_future: asr_cancel}

        # Wait for whichever finishes first. If it matched, cancel the
        # other rather than let it run to completion for no reason --
        # nothing it could still find would beat an already-confident
        # earlier-or-equal answer from "the dialogue that first appears"
        # (both sides start scanning from the same t=0).
        done, pending = wait([ocr_future, asr_future], return_when=FIRST_COMPLETED)
        if pending and any(f.result().matched for f in done):
            for f in pending:
                cancel_of[f].set()

        ocr_result = ocr_future.result()
        asr_result = asr_future.result()

    if ocr_result.matched and asr_result.matched:
        winner = ocr_result if ocr_result.timestamp_sec <= asr_result.timestamp_sec else asr_result
        logger.info(
            "Both OCR (%.2fs) and ASR (%.2fs) matched -- using earlier (%s)",
            ocr_result.timestamp_sec, asr_result.timestamp_sec, winner.source,
        )
        return winner
    if ocr_result.matched:
        logger.info("Only OCR matched (%.2fs)", ocr_result.timestamp_sec)
        return ocr_result
    if asr_result.matched:
        logger.info("Only ASR matched (%.2fs)", asr_result.timestamp_sec)
        return asr_result

    logger.warning("Neither OCR nor ASR found a confident match for %r", target_text)
    ocr_sim = ocr_result.best_near_miss.similarity if ocr_result.best_near_miss else -1.0
    asr_sim = asr_result.best_near_miss.similarity if asr_result.best_near_miss else -1.0
    return ocr_result if ocr_sim >= asr_sim else asr_result
