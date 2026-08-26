"""
Dialogue scan helpers over the same coarse sampler / preprocessing / OCR /
filtering stack as core.resolver:

  - scan_first_dialogue(): default assignment path -- walk until the *first*
    on-screen dialogue appears, then stop (pipeline refines that line for
    the exact onset frame via resolver).
  - scan_all_dialogues(): optional full-video pass -- every distinct
    on-screen line, each tagged with the earliest coarse timestamp it was
    seen at.

resolver.py answers "when does *this one* target line first appear?"
(coarse -> backward refine). dialogue_scan answers "what dialogue appears
(first / at all)?". core/pipeline.py chooses which one(s) to call.
"""
from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from core.config import settings
from core.matching.similarity import similarity_score
from core.ocr.parallel_scan import iter_scan_detections
from core.source.metadata import VideoMetadata

logger = logging.getLogger(__name__)


@dataclass
class DialogueOccurrence:
    text: str
    first_timestamp_sec: float
    frame_number: int
    confidence: float
    bbox: tuple[int, int, int, int]


def _find_existing(
    text: str, known: List[DialogueOccurrence]
) -> Optional[DialogueOccurrence]:
    """Return the known dialogue this text most likely belongs to (same
    on-screen line re-detected on a later sampled frame), or None if it
    looks like a new line."""
    best: Optional[DialogueOccurrence] = None
    best_sim = 0.0
    for occ in known:
        sim = similarity_score(text, occ.text)
        if sim > best_sim:
            best_sim, best = sim, occ
    if best is not None and best_sim >= settings.dialogue_dedup_threshold:
        return best
    return None


def _best_detection(detections) -> Optional[tuple[str, float, tuple[int, int, int, int]]]:
    """Highest-confidence plausible dialogue detection in the subtitle band,
    or None if nothing clears the OCR confidence floor."""
    best = None
    for det in detections:
        if det.confidence < settings.ocr_min_confidence:
            continue
        if best is None or det.confidence > best[1]:
            best = (det.text, det.confidence, det.bbox)
    return best


def scan_first_dialogue(
    video_path: Path, meta: VideoMetadata, on_progress=None
) -> Optional[DialogueOccurrence]:
    """
    Coarse-walk the video and stop at the first plausible on-screen dialogue.
    Returns None if no dialogue is found. Frame accuracy for that line is
    left to core.resolver.resolve() (backward ROI refine).
    """
    logger.info(
        "Dialogue scan: first-only coarse pass (interval=%.2fs)",
        settings.coarse_sample_interval_sec,
    )
    duration = max(meta.duration_sec, 1e-6)
    last_report_ts = -999.0
    with contextlib.closing(iter_scan_detections(video_path, meta, on_progress=on_progress)) as scans:
        for ts, detections in scans:
            if on_progress is not None and (ts - last_report_ts >= 2.0 or ts == 0.0):
                on_progress(
                    "scan",
                    f"Looking for first dialogue… {ts:.0f}s / {meta.duration_sec:.0f}s",
                    min(ts / duration, 0.95),
                )
                last_report_ts = ts
            best = _best_detection(detections)
            if best is None:
                continue
            text, confidence, bbox = best
            logger.info("First dialogue at %.2fs: %r -- stopping scan", ts, text)
            return DialogueOccurrence(
                text=text,
                first_timestamp_sec=ts,
                frame_number=meta.timestamp_to_frame(ts),
                confidence=confidence,
                bbox=bbox,
            )
    logger.warning("No on-screen dialogue found in coarse first-only pass")
    return None


def scan_all_dialogues(video_path: Path, meta: VideoMetadata, on_progress=None) -> List[DialogueOccurrence]:
    """
    Single coarse pass over the full video. For every OCR detection that
    survives text_filter.filter_detections, either fold it into an already
    -seen dialogue (if similar enough to one we've recorded) or record it as
    a newly-seen dialogue line at this timestamp.

    Uses the *first* interval at which a line is seen; unlike resolver.py's
    backward-refinement, this does not step back to the sub-second onset
    frame for every line (that would be one full backward-refine pass per
    detected line, which doesn't scale to "all dialogues in the video").
    Precision down to the exact onset frame is what core.resolver.resolve()
    is for, and is used for the specific target-text lookup.
    """
    dialogues: List[DialogueOccurrence] = []
    duration = max(meta.duration_sec, 1e-6)
    last_report_ts = -999.0

    logger.info("Dialogue scan: full coarse pass (interval=%.2fs)", settings.coarse_sample_interval_sec)
    with contextlib.closing(iter_scan_detections(video_path, meta, on_progress=on_progress)) as scans:
        for ts, detections in scans:
            if on_progress is not None and (ts - last_report_ts >= 2.0 or ts == 0.0):
                on_progress(
                    "scan",
                    f"Scanning all dialogues… {ts:.0f}s / {meta.duration_sec:.0f}s",
                    min(ts / duration, 0.95),
                )
                last_report_ts = ts

            for det in detections:
                if det.confidence < settings.ocr_min_confidence:
                    continue
                existing = _find_existing(det.text, dialogues)
                if existing is not None:
                    continue  # already recorded (this is the same line, later in time)
                dialogues.append(
                    DialogueOccurrence(
                        text=det.text,
                        first_timestamp_sec=ts,
                        frame_number=meta.timestamp_to_frame(ts),
                        confidence=det.confidence,
                        bbox=det.bbox,
                    )
                )
                logger.info("New dialogue at %.2fs: %r", ts, det.text)

    dialogues.sort(key=lambda d: d.first_timestamp_sec)
    return dialogues
