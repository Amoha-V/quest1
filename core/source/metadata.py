"""ffprobe wrapper: pulls fps, duration, resolution needed for sampling math."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


@dataclass
class VideoMetadata:
    duration_sec: float
    fps: float
    width: int
    height: int

    def timestamp_to_frame(self, timestamp_sec: float) -> int:
        return round(timestamp_sec * self.fps)


def probe(video_path: Path) -> VideoMetadata:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate,width,height",
        "-show_entries", "format=duration",
        "-of", "json",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    stream = data["streams"][0]
    fmt = data["format"]

    fps = float(Fraction(stream["r_frame_rate"]))
    return VideoMetadata(
        duration_sec=float(fmt["duration"]),
        fps=fps,
        width=int(stream["width"]),
        height=int(stream["height"]),
    )
