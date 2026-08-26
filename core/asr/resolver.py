"""
Speech-based counterpart to core.resolver: locates the first spoken
occurrence of `target_text` in the video's audio track via ASR transcription
+ fuzzy match, reusing the exact same core.matching.similarity scoring
core.resolver uses for OCR (same noise-tolerance logic -- ASR
misrecognition and OCR misreads are both "the text is approximately right,
score it fuzzy").

Sliding-window matching: Whisper segments are typically clause/sentence
-length chunks, and a target phrase won't always land on exactly one
segment boundary, so this concatenates up to _MAX_WINDOW consecutive
segments and scores each window -- not just single segments -- against the
target text, keeping the best-scoring window's *start* timestamp as the
onset.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import List, Optional

from core.asr.audio_extractor import extract_audio
from core.asr.transcriber import transcribe
from core.asr.types import TranscriptSegment
from core.config import settings
from core.matching.similarity import similarity_score
from core.matching.temporal_aggregator import TimestampHit
from core.resolver import ResolveResult
from core.source.metadata import VideoMetadata

logger = logging.getLogger(__name__)

_MAX_WINDOW = 4  # consecutive segments concatenated when scoring one window


def _best_window(
    segments: List[TranscriptSegment], target_text: str
) -> Optional[TimestampHit]:
    best: Optional[TimestampHit] = None
    for i in range(len(segments)):
        joined = ""
        for j in range(i, min(i + _MAX_WINDOW, len(segments))):
            joined = f"{joined} {segments[j].text}".strip() if joined else segments[j].text
            sim = similarity_score(joined, target_text)
            if best is None or sim > best.similarity:
                confidence = max(0.0, min(1.0, math.exp(segments[i].avg_logprob)))
                best = TimestampHit(
                    timestamp_sec=segments[i].start_sec,
                    text=joined,
                    confidence=confidence,
                    similarity=sim,
                    bbox=None,
                )
    return best


def resolve_audio(
    video_path: Path, meta: VideoMetadata, video_id: str, target_text: str, cancel_event=None
) -> ResolveResult:
    """
    Locate the first spoken occurrence of `target_text`. Returns the same
    ResolveResult shape core.resolver.resolve() does (source="asr"), so
    callers don't need to know which modality answered.

    `cancel_event` (optional threading.Event): checked once before starting
    -- ASR is a single one-shot transcription pass (chunked, but dispatched
    as one batch), not a steppable per-frame loop like OCR's coarse scan,
    so there's no useful mid-flight point to check it again once
    transcription has actually started.
    """
    if cancel_event is not None and cancel_event.is_set():
        logger.info("ASR resolve skipped -- already cancelled (OCR matched first)")
        return ResolveResult(matched=False, target_text=target_text, source="asr")

    audio_path = extract_audio(video_path, video_id)
    segments = transcribe(audio_path, video_id, meta.duration_sec)

    if not segments:
        logger.warning("ASR produced no speech segments for %s", video_id)
        return ResolveResult(matched=False, target_text=target_text, source="asr")

    best = _best_window(segments, target_text)
    if best is None or best.similarity < settings.text_similarity_threshold:
        logger.info(
            "No ASR match for %r (best similarity=%.2f)",
            target_text, best.similarity if best else 0.0,
        )
        return ResolveResult(
            matched=False, target_text=target_text, source="asr", best_near_miss=best
        )

    logger.info(
        "ASR match at %.2fs: %r (sim=%.2f)", best.timestamp_sec, best.text, best.similarity
    )
    return ResolveResult(
        matched=True,
        target_text=target_text,
        timestamp_sec=best.timestamp_sec,
        frame_number=meta.timestamp_to_frame(best.timestamp_sec),
        recognized_text=best.text,
        similarity=best.similarity,
        ocr_confidence=best.confidence,  # reused field name; see ResolveResult
        bbox=None,
        source="asr",
    )
