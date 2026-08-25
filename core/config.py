"""
Central configuration for the core pipeline.

Everything here is overridable via environment variables (see .env.example)
so the same code runs identically from cli.py or from service/.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Ensure ffmpeg/ffprobe are resolvable even if not on the system PATH
# (common pain point on Windows). static-ffmpeg downloads/caches static
# binaries on first use and prepends their folder to this process's PATH.
try:
    import static_ffmpeg

    static_ffmpeg.add_paths()
except Exception:  # pragma: no cover - fall back to system ffmpeg if this fails
    pass


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


@dataclass
class Settings:
    # --- paths ---
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "./outputs")))
    download_dir: Path = field(
        default_factory=lambda: Path(os.getenv("DOWNLOAD_DIR", "./outputs/_downloads"))
    )

    # --- sampling ---
    # Stage 1: coarse pass over the whole video at this interval to find
    # candidate windows where text-like regions appear.
    coarse_sample_interval_sec: float = _float("COARSE_SAMPLE_INTERVAL_SEC", 1.0)
    # Stage 2: once a candidate window is found, refine within +/- this many
    # seconds at a finer step to pin down the *first* frame the text appears on.
    roi_refine_window_sec: float = _float("ROI_REFINE_WINDOW_SEC", 1.0)
    roi_refine_step_sec: float = _float("ROI_REFINE_STEP_SEC", 0.1)

    # --- OCR / matching ---
    ocr_min_confidence: float = _float("OCR_MIN_CONFIDENCE", 0.4)
    text_similarity_threshold: float = _float("TEXT_SIMILARITY_THRESHOLD", 0.82)
    # Used only by core/dialogue_scan.py (full-video "all dialogues" scan):
    # two detections are considered the *same* dialogue line (not two
    # separate lines) when their similarity clears this bar. Deliberately
    # looser than text_similarity_threshold, which matches OCR noise against
    # one known target string; this instead decides whether two *different*
    # OCR reads refer to the same on-screen line.
    dialogue_dedup_threshold: float = _float("DIALOGUE_DEDUP_THRESHOLD", 0.85)

    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
