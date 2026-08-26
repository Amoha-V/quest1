"""
The core decision-making module: given a video and a target dialogue,
determines the exact frame where that dialogue first appears.

Two-phase strategy:
  Phase 1 (coarse):  walk the whole video (sampling.merged_sampler), running
                      OCR on each sampled frame, looking for a match against
                      the target dialogue. By default this is just
                      coarse_sampler's fixed interval; with
                      settings.change_detection_enabled, merged_sampler also
                      folds in change_detector's OCR-free candidate
                      timestamps, so short-lived dialogue that would fall
                      entirely between two coarse ticks still gets OCR'd.
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

import contextlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from core.config import settings
from core.extraction.frame_extractor import extract_frame
from core.matching.similarity import similarity_score
from core.matching.temporal_aggregator import TimestampHit, earliest_hit
from core.ocr.engine import run_dialogue_ocr
from core.ocr.parallel_scan import iter_scan_detections
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
    source: str = "ocr"  # "ocr" (on-screen text) or "asr" (spoken dialogue)


def _best_match(detections, target_text: str) -> Optional[TimestampHit]:
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


def _best_match_in_frame(frame, target_text: str) -> Optional[TimestampHit]:
    """Sequential frame->OCR->match, used only by Phase 2 refine (a handful
    of calls per run near a single anchor -- not worth parallelizing)."""
    return _best_match(run_dialogue_ocr(frame), target_text)


def resolve(
    video_path: Path,
    meta: VideoMetadata,
    target_text: str,
    *,
    stop_at_first: bool = True,
    on_progress=None,
    cancel_event=None,
) -> ResolveResult:
    """
    Locate the first frame where `target_text` appears.

    By default (`stop_at_first=True`) the coarse pass stops as soon as the
    first chronological match clears the similarity threshold -- matching
    the assignment ("the dialogue that first appears") and avoiding a full
    remaining-video walk. Pass `stop_at_first=False` to keep scanning for
    later reappearances (reported as `other_matches`).

    `on_progress(stage, message, progress)` is optional; called with
    stage "scan" during the coarse pass and "refine" during backward walk.

    `cancel_event` (optional threading.Event) is checked once per coarse
    tick -- core.combined_resolver sets it when ASR already found a
    confident match, so a scan that would otherwise run to the end of the
    video (this project's actual video has no on-screen captions at all,
    so OCR alone never stops early) doesn't keep burning CPU for an answer
    that can no longer be "the first appearance" of anything.
    """
    coarse_hits: List[TimestampHit] = []
    near_miss: Optional[TimestampHit] = None
    duration = max(meta.duration_sec, 1e-6)
    last_report_ts = -999.0

    def _report(stage: str, message: str, progress: Optional[float] = None) -> None:
        if on_progress is not None:
            on_progress(stage, message, progress)

    logger.info("Phase 1: coarse scan (interval=%.2fs)", settings.coarse_sample_interval_sec)
    if settings.subtitle_roi_enabled:
        logger.info(
            "Subtitle ROI enabled: lower %.0f%% of the frame",
            settings.subtitle_roi_height_frac * 100,
        )
    _report("scan", "Scanning frames for on-screen dialogue…", 0.0)
    with contextlib.closing(iter_scan_detections(video_path, meta, on_progress=on_progress)) as scans:
        for ts, detections in scans:
            if cancel_event is not None and cancel_event.is_set():
                logger.info("Coarse scan cancelled at %.2fs (other modality already matched)", ts)
                break
            if ts - last_report_ts >= 2.0 or ts == 0.0:
                _report(
                    "scan",
                    f"Scanning frames… {ts:.0f}s / {meta.duration_sec:.0f}s",
                    min(ts / duration, 0.95),
                )
                last_report_ts = ts
            best = _best_match(detections, target_text)
            if best is None:
                continue
            best.timestamp_sec = ts

            if best.similarity >= settings.text_similarity_threshold:
                logger.info("Coarse match at %.2fs: %r (sim=%.2f)", ts, best.text, best.similarity)
                coarse_hits.append(best)
                if stop_at_first:
                    logger.info("Stopping coarse scan at first match (%.2fs)", ts)
                    break
            elif near_miss is None or best.similarity > near_miss.similarity:
                near_miss = best

    if not coarse_hits:
        logger.warning("No coarse match found for target text %r", target_text)
        return ResolveResult(matched=False, target_text=target_text, best_near_miss=near_miss)

    # Use the first coarse hit chronologically as the anchor to refine from.
    anchor = min(coarse_hits, key=lambda h: h.timestamp_sec)
    other_matches = [h for h in coarse_hits if h is not anchor]

    logger.info("Phase 2: refining backward from %.2fs", anchor.timestamp_sec)
    _report(
        "refine",
        f"Pinning exact first frame near {anchor.timestamp_sec:.1f}s…",
        0.96,
    )
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
