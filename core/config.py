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


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


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

    # Optional add-on stage (core/sampling/change_detector.py): a fine-interval,
    # OCR-free pixel-diff pass over the subtitle band that catches dialogue
    # short enough to fall entirely between two coarse_sample_interval_sec
    # ticks. Off by default -- coarse_sampler.py alone is unaffected either way.
    change_detection_enabled: bool = _bool("CHANGE_DETECTION_ENABLED", False)
    change_detect_interval_sec: float = _float("CHANGE_DETECT_INTERVAL_SEC", 0.15)
    # Mean absolute grayscale difference (0-255) between consecutive fine
    # samples of the subtitle band required to flag a candidate timestamp.
    change_detect_threshold: float = _float("CHANGE_DETECT_THRESHOLD", 12.0)

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

    # --- ASR (spoken dialogue) ---
    # Runs concurrently with the OCR scan (core.combined_resolver) so target
    # text is found whether it's shown as on-screen text or only spoken --
    # a video can have either, and OCR alone can never succeed on the latter
    # no matter how long it scans.
    # base.en over small.en: matching only needs "close enough" text for
    # rapidfuzz to score, not publication-quality transcription, so the
    # smaller/faster model is the better default here.
    asr_model_size: str = os.getenv("ASR_MODEL_SIZE", "base.en")
    asr_language: str = os.getenv("ASR_LANGUAGE", "en")
    asr_vad_filter: bool = _bool("ASR_VAD_FILTER", True)
    # Chunked parallel transcription (core/asr/parallel_transcriber.py):
    # splits the audio into this many pieces and transcribes them
    # concurrently, each in its own single-threaded WhisperModel process,
    # instead of one model instance using several intra-op threads --
    # CTranslate2 inference has diminishing returns much past 2-4 threads
    # for one stream, so splitting the *work* scales more cleanly. Static
    # core split with the OCR worker pool (core.ocr.parallel_scan defaults
    # to cpu_count-1, capped at 8) so the two don't oversubscribe the same
    # machine when running at once via core.combined_resolver. Not
    # adaptive -- tune per box. Measured on this project's dev machine
    # (16GB RAM, ~3-4GB actually free with Docker/IDE/etc already running):
    # 4 concurrent WhisperModel loads alongside OCR's 8 workers exhausted
    # available memory and crashed (BrokenProcessPool, Rust allocator
    # failure) -- default kept low because of that, not just as a guess.
    asr_chunk_workers: int = int(os.getenv("ASR_CHUNK_WORKERS", "2"))

    # Spatial ROI: only OCR the lower subtitle/dialogue band so watermarks
    # and titles in the top/corners (e.g. "Releasing April 29") are ignored.
    subtitle_roi_enabled: bool = _bool("SUBTITLE_ROI_ENABLED", True)
    subtitle_roi_top_frac: float = _float("SUBTITLE_ROI_TOP_FRAC", 0.70)
    subtitle_roi_height_frac: float = _float("SUBTITLE_ROI_HEIGHT_FRAC", 0.30)

    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
