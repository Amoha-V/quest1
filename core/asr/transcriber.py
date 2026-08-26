"""
Speech-to-text over the full audio track. Transcription itself is
core.asr.parallel_transcriber.transcribe_parallel() (chunked across worker
processes -- see that module's docstring for why); this module owns the
caching layer around it: a video's transcript is a one-shot, expensive
result we don't want to recompute across resolver runs for the same video,
so it's written to a JSON file per video_id and reused on subsequent calls.
Matching a target phrase against an already-cached transcript
(core.asr.resolver) is then near-instant.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List

from core.asr.parallel_transcriber import transcribe_parallel
from core.asr.types import TranscriptSegment
from core.config import settings

logger = logging.getLogger(__name__)


def _transcript_cache_path(video_id: str) -> Path:
    return settings.output_dir / video_id / "transcript.json"


def transcribe(audio_path: Path, video_id: str, duration_sec: float) -> List[TranscriptSegment]:
    cache_path = _transcript_cache_path(video_id)
    if cache_path.exists():
        logger.info("Using cached transcript for %s -> %s", video_id, cache_path)
        data = json.loads(cache_path.read_text())
        return [TranscriptSegment(**d) for d in data]

    work_dir = settings.output_dir / video_id / "_asr_chunks"
    result = transcribe_parallel(audio_path, duration_sec, work_dir)
    logger.info("Transcribed %d segment(s) for %s", len(result), video_id)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps([s.__dict__ for s in result], indent=2))
    return result
