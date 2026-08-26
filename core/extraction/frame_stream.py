"""
Cheap complement to frame_extractor.extract_frame(): decodes the video with
a single long-lived ffmpeg process instead of spawning a fresh one (with its
own -ss seek) for every coarse timestamp.

frame_extractor.extract_frame() is deliberately left untouched and still
used everywhere else (backward refine in resolver.py, the final result-frame
save in pipeline.py, the fine-grained change_detector.py pass) -- those are
each a handful of calls per run. This module targets specifically the hot
path: resolver.py / dialogue_scan.py's forward, uniform-interval coarse walk,
which is the O(video_duration / interval) loop that dominates wall-clock
time on a long video (~3262 separate ffmpeg process spawns + keyframe
reseeks for a ~54min video at the default 1s interval).

Scope/limitation: this only covers a *uniform* interval walk (plain
coarse_timestamps()), expressed to ffmpeg as "every Kth decoded frame" via
a single select filter -- much cheaper to construct than one filter term
per timestamp, and avoids piping the entire native-rate frame stream back to
Python (which would be hundreds of GB for a long video) by having ffmpeg
itself discard the frames we don't want. It does NOT support the irregular
union of timestamps merged_sampler.py produces when
settings.change_detection_enabled is on -- callers must fall back to
extract_frame()-per-timestamp in that case (see resolver.py / dialogue_scan.py).

Approximation note: because K is an integer frame stride, the emitted
timestamps (frame_index / fps) can drift by a few milliseconds per step from
coarse_timestamps()'s exact wall-clock seconds on non-integer-fps video
(e.g. 29.97fps), accumulating to a few seconds by the end of a very long
video. This is harmless: the coarse pass only needs to land *within* a
dialogue line's on-screen window to trigger Phase 2 (roi_sampler backward
refine), which re-derives the exact onset timestamp regardless of which
coarse tick triggered the match.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Iterator, Optional, Tuple

import numpy as np

from core.config import settings
from core.extraction.frame_extractor import extract_frame
from core.source.metadata import VideoMetadata

logger = logging.getLogger(__name__)

_BYTES_PER_PIXEL = 3  # bgr24


def coarse_frame_stride(meta: VideoMetadata, interval_sec: float) -> int:
    return max(1, round(meta.fps * interval_sec))


def stream_coarse_frames(
    video_path: Path, meta: VideoMetadata, interval_sec: float
) -> Iterator[Tuple[float, np.ndarray]]:
    """
    Yield (timestamp_sec, frame) for every Kth decoded frame (K derived from
    `interval_sec` and meta.fps), decoding the whole file with one ffmpeg
    process rather than one process+seek per timestamp.

    Stopping iteration early (breaking out of the consuming for-loop) leaves
    the generator suspended holding an open subprocess; wrap consumption in
    `contextlib.closing(...)` so `break` promptly terminates ffmpeg instead
    of leaving it decoding the remainder of the video in the background.
    """
    stride = coarse_frame_stride(meta, interval_sec)
    frame_bytes = meta.width * meta.height * _BYTES_PER_PIXEL

    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vf", f"select=not(mod(n\\,{stride}))",
        "-fps_mode", "passthrough",
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-loglevel", "error",
        "-",
    ]
    logger.info(
        "Streaming coarse decode: stride=%d frames (~%.2fs), one ffmpeg process for the whole scan",
        stride, stride / max(meta.fps, 1e-6),
    )
    proc: Optional[subprocess.Popen] = None
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=frame_bytes * 2)
        emitted = 0
        while True:
            raw = proc.stdout.read(frame_bytes)
            if len(raw) < frame_bytes:
                break
            frame = np.frombuffer(raw, dtype=np.uint8).reshape((meta.height, meta.width, 3))
            ts = round((emitted * stride) / meta.fps, 3)
            yield ts, frame
            emitted += 1
    finally:
        if proc is not None:
            if proc.stdout is not None:
                proc.stdout.close()
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def iter_scan_frames(
    video_path: Path, meta: VideoMetadata, on_progress=None
) -> Iterator[Tuple[float, np.ndarray]]:
    """
    (timestamp, frame) pairs for a coarse/dialogue scan loop -- the single
    seam resolver.py / dialogue_scan.py use to get frames for their walk.

    Uses the fast single-process stream_coarse_frames() when
    settings.change_detection_enabled is off (the default -- and the only
    case stream_coarse_frames supports, see its docstring above). Falls back
    to the original per-timestamp extract_frame() over
    merged_sampler.sample_timestamps() when change detection is on, since
    that produces an irregular timestamp union stream_coarse_frames can't
    express as a single ffmpeg select filter.

    Wrap consumption in contextlib.closing(...) so an early `break`
    (stop_at_first) promptly tears down the ffmpeg process instead of
    leaving it decoding the rest of the video in the background.
    """
    if not settings.change_detection_enabled:
        yield from stream_coarse_frames(video_path, meta, settings.coarse_sample_interval_sec)
        return

    from core.sampling.merged_sampler import sample_timestamps

    for ts in sample_timestamps(video_path, meta, on_progress=on_progress):
        yield ts, extract_frame(video_path, ts, meta)
