"""
Extracts a video's audio track to a 16kHz mono WAV file -- the format
faster-whisper/CTranslate2 expects. Cached alongside the downloaded video
(keyed by video_id, same directory core.source.downloader uses) since
transcription is a one-shot, expensive step we don't want to repeat across
resolver runs for the same video.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from core.config import settings

logger = logging.getLogger(__name__)

_SAMPLE_RATE_HZ = 16000


def extract_audio(video_path: Path, video_id: str) -> Path:
    settings.ensure_dirs()
    audio_path = settings.download_dir / f"{video_id}.wav"
    if audio_path.exists():
        logger.info("Using cached audio extraction for %s -> %s", video_id, audio_path)
        return audio_path

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",
        "-ac", "1",
        "-ar", str(_SAMPLE_RATE_HZ),
        "-f", "wav",
        "-loglevel", "error",
        str(audio_path),
    ]
    logger.info("Extracting audio track from %s -> %s", video_path, audio_path)
    subprocess.run(cmd, check=True)
    return audio_path
