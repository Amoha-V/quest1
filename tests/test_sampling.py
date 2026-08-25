from core.sampling.coarse_sampler import coarse_timestamps
from core.sampling.roi_sampler import refine_timestamps_before
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
