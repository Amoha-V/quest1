"""
Single seam resolver.py / dialogue_scan.py call into for "which timestamps
do we OCR" -- merges coarse_sampler.py's fixed-interval timestamps with
change_detector.py's cheap-diff candidate timestamps.

This is what makes change detection additive rather than a replacement:
with settings.change_detection_enabled=False this returns exactly
coarse_timestamps(meta), unchanged, and change_detector.py's fine pass
never runs.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from core.sampling.change_detector import detect_change_timestamps
from core.sampling.coarse_sampler import coarse_timestamps
from core.source.metadata import VideoMetadata


def sample_timestamps(
    video_path: Path, meta: VideoMetadata, on_progress=None
) -> Iterator[float]:
    """
    Sorted, de-duplicated union of coarse_timestamps(meta) and (when enabled)
    detect_change_timestamps(...) -- the full set of timestamps the OCR loop
    in resolver.py / dialogue_scan.py should visit.
    """
    coarse = list(coarse_timestamps(meta))
    changed = detect_change_timestamps(video_path, meta, on_progress=on_progress)
    if not changed:
        return iter(coarse)
    return iter(sorted(set(coarse) | set(changed)))
