"""
The core decision-making module: given a video and a target dialogue,
determines the exact frame where that dialogue first appears.

Two-phase strategy:
  Phase 1 (coarse):  walk the whole video at a fixed interval (coarse_sampler)
                      running OCR on each sampled frame, looking for a match
                      against the target dialogue.
  Phase 2 (refine):   once a coarse match is found, step backward in fine
                      increments (roi_sampler.refine_timestamps_before) to
                      find the earliest timestamp where the text is still
                      present -- this is reported as the "first frame".

Ambiguity handling:
  - If multiple distinct text regions match the target above threshold in
    the same coarse pass (e.g. text re-appears later in the video), we
    report the first occurrence and flag the rest as `other_matches` in the
    result rather than silently discarding them.
  - If no detection clears `settings.text_similarity_threshold`, we return
    a result with `matched=False` and the *closest* candidate we did see,
    so the failure mode is inspectable instead of silent.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from core.config import settings
from core.extraction.frame_extractor import extract_frame
from core.matching.similarity import similarity_score
from core.matching.temporal_aggregator import TimestampHit, earliest_hit
from core.matching.text_filter import filter_detections
from core.ocr.engine import run_ocr
from core.preprocessing.frame_preprocessor import preprocess
from core.sampling.coarse_sampler import coarse_timestamps
from core.sampling.roi_sampler import refine_timestamps_before
from core.source.metadata import VideoMetadata

logger = logging.getLogger(__name__)


@dataclass
class ResolveResult:
    matched: bool
    target_text: str
    timestamp_sec: Optional[float] = None
    frame_number: Optional[int] = None
    recognized_text: Optional[str] = None
    similarity: Optional[float] = None
    ocr_confidence: Optional[float] = None
    bbox: Optional[tuple[int, int, int, int]] = None
    other_matches: List[TimestampHit] = field(default_factory=list)
    best_near_miss: Optional[TimestampHit] = None  # populated when matched=False


def _best_match_in_frame(frame, target_text: str) -> Optional[TimestampHit]:
    detections = filter_detections(run_ocr(preprocess(frame)))
    best: Optional[TimestampHit] = None
    for det in detections:
        sim = similarity_score(det.text, target_text)
        if best is None or sim > best.similarity:
            best = TimestampHit(
                timestamp_sec=-1.0,  # filled in by caller
                text=det.text,
                confidence=det.confidence,
                similarity=sim,
                bbox=det.bbox,
            )
    return best


def resolve(video_path: Path, meta: VideoMetadata, target_text: str) -> ResolveResult:
    coarse_hits: List[TimestampHit] = []
    near_miss: Optional[TimestampHit] = None

    logger.info("Phase 1: coarse scan (interval=%.2fs)", settings.coarse_sample_interval_sec)
    for ts in coarse_timestamps(meta):
        frame = extract_frame(video_path, ts, meta)
        best = _best_match_in_frame(frame, target_text)
        if best is None:
            continue
        best.timestamp_sec = ts

        if best.similarity >= settings.text_similarity_threshold:
            logger.info("Coarse match at %.2fs: %r (sim=%.2f)", ts, best.text, best.similarity)
            coarse_hits.append(best)
        elif near_miss is None or best.similarity > near_miss.similarity:
            near_miss = best

    if not coarse_hits:
        logger.warning("No coarse match found for target text %r", target_text)
        return ResolveResult(matched=False, target_text=target_text, best_near_miss=near_miss)

    # Use the first coarse hit chronologically as the anchor to refine from.
    anchor = min(coarse_hits, key=lambda h: h.timestamp_sec)
    other_matches = [h for h in coarse_hits if h is not anchor]

    logger.info("Phase 2: refining backward from %.2fs", anchor.timestamp_sec)
    refine_hits: List[TimestampHit] = [anchor]
    for ts in refine_timestamps_before(anchor.timestamp_sec):
        if ts == anchor.timestamp_sec:
            continue
        frame = extract_frame(video_path, ts, meta)
        best = _best_match_in_frame(frame, target_text)
        if best is not None and best.similarity >= settings.text_similarity_threshold:
            best.timestamp_sec = ts
            refine_hits.append(best)
        else:
            # text no longer present -- we've stepped before its onset.
            break

    first_hit = earliest_hit(refine_hits)
    frame_number = meta.timestamp_to_frame(first_hit.timestamp_sec)

    return ResolveResult(
        matched=True,
        target_text=target_text,
        timestamp_sec=first_hit.timestamp_sec,
        frame_number=frame_number,
        recognized_text=first_hit.text,
        similarity=first_hit.similarity,
        ocr_confidence=first_hit.confidence,
        bbox=first_hit.bbox,
        other_matches=other_matches,
    )
