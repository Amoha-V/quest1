"""
Cheap, OCR-free companion to coarse_sampler.py.

coarse_sampler.py walks the video at a fixed interval (default 1s) and
resolver.py / dialogue_scan.py OCR every one of those ticks. If a dialogue
line appears and disappears entirely within one interval, no coarse tick
ever lands inside its on-screen window, so it's never sampled -- and no
downstream layer (OCR, similarity, roi_sampler's backward refine) can
recover a window that was never looked at.

This module doesn't fix that by running OCR more often (too expensive to run
at fine granularity across a whole video). Instead it walks the video at a
much finer interval doing only a pixel-level diff of the subtitle band --
no OCR, no text recognition -- and flags timestamps where that band visibly
changed. Those candidate timestamps get folded in by
sampling/merged_sampler.py, which is what actually gets OCR'd.

Deliberately opt-in (settings.change_detection_enabled, default False).
coarse_sampler.py, resolver.py's OCR/similarity logic, and roi_sampler.py's
backward refine are all untouched by this module.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator, List, Optional

import cv2
import numpy as np

from core.config import settings
from core.extraction.frame_extractor import extract_frame
from core.sampling.roi_sampler import subtitle_band
from core.source.metadata import VideoMetadata

logger = logging.getLogger(__name__)

# Downscale target for the diffed band -- keeps the diff cheap and robust to
# single-pixel/compression noise; large enough that real text entering or
# leaving the band still moves the mean.
_SIGNATURE_SIZE = (160, 48)  # (width, height)


def fine_timestamps(meta: VideoMetadata) -> Iterator[float]:
    """Yield candidate timestamps at settings.change_detect_interval_sec --
    much finer than coarse_timestamps(), but never OCR'd by this module."""
    t = 0.0
    step = settings.change_detect_interval_sec
    while t < meta.duration_sec:
        yield round(t, 3)
        t += step


def _band_signature(frame: np.ndarray, roi) -> np.ndarray:
    """Small grayscale crop of the subtitle band, used only for a pixel
    diff -- never fed to OCR."""
    if roi is not None:
        x, y, w, h = roi
        frame = frame[y : y + h, x : x + w]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, _SIGNATURE_SIZE, interpolation=cv2.INTER_AREA)


def _changed(prev: Optional[np.ndarray], curr: np.ndarray) -> bool:
    if prev is None:
        return False
    diff = cv2.absdiff(prev, curr)
    return float(diff.mean()) >= settings.change_detect_threshold


def detect_change_timestamps(
    video_path: Path, meta: VideoMetadata, on_progress=None
) -> List[float]:
    """
    Walk the video at a fine interval, diffing only the subtitle band
    frame-to-frame (no OCR). Returns timestamps where that band changed
    enough to plausibly be text appearing/disappearing -- candidates the
    coarse OCR pass may have stepped over entirely.

    Returns [] immediately if settings.change_detection_enabled is False.
    """
    if not settings.change_detection_enabled:
        return []

    duration = max(meta.duration_sec, 1e-6)
    last_report_ts = -999.0
    roi = subtitle_band(meta.width, meta.height)

    prev_sig: Optional[np.ndarray] = None
    changed_ts: List[float] = []

    logger.info(
        "Change detection: fine pass (interval=%.2fs, threshold=%.1f)",
        settings.change_detect_interval_sec,
        settings.change_detect_threshold,
    )
    for ts in fine_timestamps(meta):
        if on_progress is not None and (ts - last_report_ts >= 2.0 or ts == 0.0):
            on_progress(
                "change_scan",
                f"Checking for short-lived dialogue… {ts:.0f}s / {meta.duration_sec:.0f}s",
                min(ts / duration, 0.95),
            )
            last_report_ts = ts

        frame = extract_frame(video_path, ts, meta)
        sig = _band_signature(frame, roi)
        if _changed(prev_sig, sig):
            changed_ts.append(ts)
        prev_sig = sig

    logger.info("Change detection found %d candidate timestamp(s)", len(changed_ts))
    return changed_ts
