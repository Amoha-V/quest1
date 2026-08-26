"""
ROI-based refinement sampling.

Once the coarse pass (coarse_sampler.py) finds a timestamp where the target
dialogue text is detected, on-screen dialogue/subtitle text almost always
persists for a short span rather than appearing on a single frame. We don't
know the *exact* onset frame from one coarse hit, so we step backwards in
fine increments from the coarse hit to find the earliest frame where the
text region is still present -- that's the "first frame" the assignment
asks for.

This also gives us the region of interest (bounding box) for that text,
which speeds up preprocessing/OCR on neighboring frames since we can crop
instead of scanning the full frame.
"""
from __future__ import annotations

from typing import Iterator, Tuple

from core.config import settings


def refine_timestamps_before(hit_timestamp: float) -> Iterator[float]:
    """
    Yield fine-grained timestamps stepping backward from a coarse hit,
    down to `hit_timestamp - roi_refine_window_sec`, so the resolver can
    find the earliest frame at which the text is already present.
    """
    window = settings.roi_refine_window_sec
    step = settings.roi_refine_step_sec
    t = hit_timestamp
    lower_bound = max(0.0, hit_timestamp - window)
    while t >= lower_bound:
        yield round(t, 3)
        t -= step


BBox = Tuple[int, int, int, int]  # x, y, w, h


def subtitle_band(frame_w: int, frame_h: int) -> BBox | None:
    """Lower-third crop used for dialogue OCR. Returns None when disabled."""
    if not settings.subtitle_roi_enabled:
        return None
    top_frac = min(max(settings.subtitle_roi_top_frac, 0.0), 0.95)
    height_frac = min(max(settings.subtitle_roi_height_frac, 0.05), 1.0)
    y = int(frame_h * top_frac)
    h = max(1, int(frame_h * height_frac))
    if y + h > frame_h:
        h = frame_h - y
    if h <= 0:
        return None
    return (0, y, frame_w, h)
