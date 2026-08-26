from core.config import settings
from core.ocr.engine import offset_detections
from core.ocr.types import OcrDetection
from core.sampling.coarse_sampler import coarse_timestamps
from core.sampling.roi_sampler import refine_timestamps_before, subtitle_band
from core.source.metadata import VideoMetadata


def test_coarse_timestamps_cover_full_duration():
    meta = VideoMetadata(duration_sec=5.0, fps=30.0, width=1920, height=1080)
    ts = list(coarse_timestamps(meta))
    assert ts[0] == 0.0
    assert ts[-1] < 5.0
    assert all(b - a > 0 for a, b in zip(ts, ts[1:]))  # strictly increasing


def test_refine_steps_backward_within_window():
    ts = list(refine_timestamps_before(10.0))
    assert ts[0] == 10.0
    assert min(ts) >= 9.0  # default roi_refine_window_sec = 1.0
    assert all(a >= b for a, b in zip(ts, ts[1:]))  # non-increasing


def test_subtitle_band_covers_bottom_third_only():
    roi = subtitle_band(1920, 1080)
    assert roi is not None
    x, y, w, h = roi
    assert x == 0
    assert w == 1920
    assert y == int(1080 * settings.subtitle_roi_top_frac)
    assert y + h == 1080 or abs((y + h) - 1080) < 2
    # top-right watermark region is above the band
    assert y > 1080 * 0.5


def test_offset_detections_maps_crop_coords_to_full_frame():
    det = OcrDetection(text="hello", confidence=0.9, bbox=(10, 5, 40, 12))
    out = offset_detections([det], origin_x=0, origin_y=756)
    assert out[0].bbox == (10, 761, 40, 12)
