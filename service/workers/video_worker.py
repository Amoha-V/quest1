"""
Background task runner that calls core.pipeline.process_video_full() off
the request thread, so service/routers/videos.py's POST /videos/process
can return a job_id immediately and the client polls
GET /videos/{id}/status until it flips to "done"/"error", then fetches
GET /videos/{id}/results.

Uses a plain ThreadPoolExecutor rather than Celery/RQ: the pipeline is
CPU/IO-bound Python (ffmpeg subprocess + OCR), a thread pool parallelizes
it across requests just fine for a demo service, and it avoids requiring a
broker on top of the diagram's existing Redis/Postgres/MinIO. Swapping in
Celery later would only mean replacing submit_job()'s body -- routers and
status/result plumbing (Redis/Postgres) stay the same.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from core.config import settings
from core.pipeline import process_video_full
from core.source.downloader import video_id_for
from service.cache import redis_client
from service.db.models import Dialogue, TargetMatch, Video
from service.db.session import get_session
from service.storage import minio_client

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="video-worker")


def job_id_for(url: str, target_text: Optional[str]) -> str:
    video_id = video_id_for(url)
    if not target_text:
        return video_id
    import hashlib

    text_hash = hashlib.sha1(target_text.encode("utf-8")).hexdigest()[:8]
    return f"{video_id}:{text_hash}"


def submit_job(url: str, target_text: Optional[str] = None, force: bool = False) -> str:
    """Enqueue processing for `url` (+ optional `target_text`). Returns the
    job_id the client should poll. Safe to call repeatedly for the same
    (url, target_text) -- job status is idempotent and core.pipeline has
    its own on-disk result caching, so a duplicate submission is cheap
    once the first has completed."""
    job_id = job_id_for(url, target_text)
    video_id = video_id_for(url)

    existing = redis_client.get_job_status(job_id)
    if existing and existing["status"] in (redis_client.STATUS_PENDING, redis_client.STATUS_PROCESSING):
        logger.info("Job %s already in flight, not re-submitting", job_id)
        return job_id

    redis_client.set_job_status(job_id, redis_client.STATUS_PENDING, video_id=video_id)
    _executor.submit(_run_job, job_id, video_id, url, target_text, force)
    return job_id


def _run_job(job_id: str, video_id: str, url: str, target_text: Optional[str], force: bool) -> None:
    redis_client.set_job_status(job_id, redis_client.STATUS_PROCESSING, video_id=video_id)
    try:
        result = process_video_full(url, target_text=target_text, force=force)
        _persist_result(video_id, url, result)
        redis_client.cache_result(job_id, result)
        redis_client.set_job_status(job_id, redis_client.STATUS_DONE, video_id=video_id)
        logger.info("Job %s done (%d dialogues)", job_id, len(result["dialogues"]))
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        redis_client.set_job_status(job_id, redis_client.STATUS_ERROR, video_id=video_id, error=str(exc))


def _persist_result(video_id: str, url: str, result: dict) -> None:
    """Upsert Video/Dialogue/TargetMatch rows and push frame images to
    MinIO (falling back to local paths if MinIO isn't reachable -- see
    service/storage/minio_client.py)."""
    with get_session() as session:
        video = session.get(Video, video_id)
        if video is None:
            video = Video(id=video_id, url=url)
            session.add(video)

        video.status = "done"
        video.error_message = None
        video.duration_sec = result.get("duration_sec")
        video.fps = result.get("fps")

        # Replace this video's dialogue rows with the freshly-scanned set.
        session.query(Dialogue).filter(Dialogue.video_id == video_id).delete()
        for d in result["dialogues"]:
            object_key = minio_client.upload_frame(
                d["frame_image_path"], f"{video_id}/dialogues/{d['index']:04d}.png"
            )
            session.add(
                Dialogue(
                    video_id=video_id,
                    idx=d["index"],
                    text=d["text"],
                    timestamp_sec=d["timestamp_sec"],
                    frame_number=d["frame_number"],
                    confidence=d["confidence"],
                    bbox=list(d["bbox"]) if d["bbox"] else None,
                    frame_object_key=object_key,
                )
            )

        target = result.get("target_match")
        if target:
            object_key = None
            if target.get("frame_image_path"):
                import hashlib

                text_hash = hashlib.sha1(target["target_text"].encode("utf-8")).hexdigest()[:8]
                object_key = minio_client.upload_frame(
                    target["frame_image_path"], f"{video_id}/targets/{text_hash}.png"
                )
            session.add(
                TargetMatch(
                    video_id=video_id,
                    target_text=target["target_text"],
                    matched=target["matched"],
                    timestamp_sec=target.get("timestamp_sec"),
                    frame_number=target.get("frame_number"),
                    recognized_text=target.get("recognized_text"),
                    similarity=target.get("similarity"),
                    ocr_confidence=target.get("ocr_confidence"),
                    bbox=list(target["bbox"]) if target.get("bbox") else None,
                    frame_object_key=object_key,
                )
            )
