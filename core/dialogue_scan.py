"""
Full-video dialogue scan: walks the whole video once (reusing the same
coarse sampler / preprocessing / OCR / filtering modules as core.resolver)
and returns *every distinct* on-screen dialogue line detected, each tagged
with the earliest timestamp/frame it was seen at.

This is a separate module from core/resolver.py on purpose:
  - resolver.py answers "when does *this one* target line first appear?"
    (coarse pass -> backward refine -> single answer)
  - dialogue_scan.py answers "what dialogue lines appear in this video at
    all?" (single coarse pass -> dedup -> many answers)

They're both thin orchestrators over the same lower-level modules
(core/sampling, core/preprocessing, core/ocr, core/matching), so neither
duplicates OCR/matching logic -- they just compose it differently for two
different questions. core/pipeline.py decides which one(s) to call.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from core.config import settings
from core.extraction.frame_extractor import extract_frame
from core.matching.similarity import similarity_score
from core.matching.text_filter import filter_detections
from core.ocr.engine import run_ocr
from core.preprocessing.frame_preprocessor import preprocess
from core.sampling.coarse_sampler import coarse_timestamps
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


def scan_all_dialogues(video_path: Path, meta: VideoMetadata) -> List[DialogueOccurrence]:
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

    logger.info("Dialogue scan: coarse pass (interval=%.2fs)", settings.coarse_sample_interval_sec)
    for ts in coarse_timestamps(meta):
        frame = extract_frame(video_path, ts, meta)
        detections = filter_detections(run_ocr(preprocess(frame)))

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
