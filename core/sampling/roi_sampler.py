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


def expand_bbox(bbox: BBox, frame_w: int, frame_h: int, pad_ratio: float = 0.15) -> BBox:
    """Pad a detected text bbox slightly so cropped re-checks on nearby
    frames don't clip text that shifts a few pixels between frames."""
    x, y, w, h = bbox
    pad_x = int(w * pad_ratio)
    pad_y = int(h * pad_ratio)
    x2 = max(0, x - pad_x)
    y2 = max(0, y - pad_y)
    w2 = min(frame_w - x2, w + 2 * pad_x)
    h2 = min(frame_h - y2, h + 2 * pad_y)
    return x2, y2, w2, h2
