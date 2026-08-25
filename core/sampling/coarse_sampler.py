"""
Coarse temporal sampling: walk the whole video at a fixed interval and
extract a frame at each step. This is the fallback strategy used when no
prior ROI is known (e.g. first pass on a video, or ROI sampling found
nothing plausible).

Trade-off: cheap and simple, but can miss dialogue that appears and
disappears entirely within one interval. roi_refine_* in sampling/roi_sampler.py
compensates for this once a candidate window is found.
"""
from __future__ import annotations

from typing import Iterator

from core.config import settings
from core.source.metadata import VideoMetadata


def coarse_timestamps(meta: VideoMetadata) -> Iterator[float]:
    """Yield candidate timestamps (seconds) across the full video duration."""
    t = 0.0
    step = settings.coarse_sample_interval_sec
    while t < meta.duration_sec:
        yield round(t, 3)
        t += step
