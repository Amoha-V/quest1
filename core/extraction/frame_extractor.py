"""Pulls a single frame at a given timestamp using ffmpeg, as a numpy/BGR array."""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from core.source.metadata import VideoMetadata


def extract_frame(video_path: Path, timestamp_sec: float, meta: VideoMetadata) -> np.ndarray:
    """
    Seek to `timestamp_sec` and decode exactly one frame, returned as an
    OpenCV-style BGR numpy array (H, W, 3).

    Uses -ss before -i for fast (keyframe-adjacent) seeking, then a small
    output frame count of 1 to grab the nearest decodable frame.
    """
    cmd = [
        "ffmpeg",
        "-ss", f"{timestamp_sec:.3f}",
        "-i", str(video_path),
        "-frames:v", "1",
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-loglevel", "error",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, check=True)
    frame = np.frombuffer(result.stdout, dtype=np.uint8)
    frame = frame.reshape((meta.height, meta.width, 3))
    return frame


def save_frame(frame: np.ndarray, out_path: Path) -> Path:
    import cv2

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), frame)
    return out_path
