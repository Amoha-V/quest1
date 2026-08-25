"""
Resolves an arbitrary video URL (YouTube, ok.ru, direct file, etc.) down to a
local file path that ffmpeg/ffprobe can operate on.

Uses yt-dlp because it supports a very wide range of hosts (including ok.ru,
the host used in the assignment's sample URL) with one consistent interface.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import yt_dlp

from core.config import settings

logger = logging.getLogger(__name__)


def video_id_for(url: str) -> str:
    """Stable short hash used as a directory/cache key for a given URL."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def download_video(url: str) -> Path:
    """
    Download `url` (if not already cached) and return the local file path.

    Idempotent: if a file for this URL's video_id already exists in
    download_dir, it's reused instead of re-downloading.
    """
    settings.ensure_dirs()
    vid = video_id_for(url)
    target_stub = settings.download_dir / vid

    existing = list(settings.download_dir.glob(f"{vid}.*"))
    if existing:
        logger.info("Using cached download for %s -> %s", url, existing[0])
        return existing[0]

    ydl_opts = {
        "outtmpl": str(target_stub) + ".%(ext)s",
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    logger.info("Downloading %s ...", url)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = Path(ydl.prepare_filename(info))

    if not filepath.exists():
        # some extractors/postprocessors change the extension after merge
        matches = list(settings.download_dir.glob(f"{vid}.*"))
        if not matches:
            raise FileNotFoundError(f"yt-dlp reported success but no file found for {url}")
        filepath = matches[0]

    logger.info("Downloaded to %s", filepath)
    return filepath
