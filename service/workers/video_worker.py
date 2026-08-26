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

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from core.pipeline import process_video_full
from core.source.downloader import video_id_for
from service.cache import redis_client
from service.db.models import Dialogue, TargetMatch, Video
from service.db.session import get_session
from service.storage import minio_client

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="video-worker")


def normalize_dialogue(text: Optional[str]) -> str:
    """Stable cache key for a dialogue line: trim, collapse spaces, casefold."""
    if not text:
        return ""
    return " ".join(text.split()).casefold()


def job_id_for(url: str, target_text: Optional[str], scan_all: bool = False) -> str:
    video_id = video_id_for(url)
    parts = [video_id]
    norm = normalize_dialogue(target_text)
    if norm:
        parts.append(hashlib.sha1(norm.encode("utf-8")).hexdigest()[:8])
    # Keep first-only vs full-scan jobs distinct so toggling the option
    # does not reuse the wrong cached result.
    parts.append("all" if scan_all else "first")
    return ":".join(parts)


def _postgres_has_result(
    video_id: str, target_text: Optional[str], scan_all: bool
) -> bool:
    """True when Postgres already has a completed result for this lookup."""
    with get_session() as session:
        video = session.get(Video, video_id)
        if video is None or video.status != "done":
            return False
        dialogue_count = (
            session.query(Dialogue).filter(Dialogue.video_id == video_id).count()
        )
        if scan_all:
            return dialogue_count > 1
        wanted = normalize_dialogue(target_text)
        if wanted:
            matches = (
                session.query(TargetMatch)
                .filter(TargetMatch.video_id == video_id)
                .all()
            )
            return any(normalize_dialogue(m.target_text) == wanted for m in matches)
        return dialogue_count >= 1 or (
            session.query(TargetMatch).filter(TargetMatch.video_id == video_id).count() >= 1
        )


def _mark_cache_hit(job_id: str, video_id: str, source: str) -> None:
    redis_client.set_job_status(
        job_id,
        redis_client.STATUS_DONE,
        video_id=video_id,
        stage="done",
        message=f"Cache hit ({source}) — skipped pipeline",
        progress=1.0,
        cached=True,
        error=None,
    )


def submit_job(
    url: str,
    target_text: Optional[str] = None,
    force: bool = False,
    scan_all: bool = False,
) -> str:
    """Enqueue processing for `url` (+ optional `target_text`). Returns the
    job_id the client should poll.

    Cache key is (video URL, normalized dialogue, scan_all). On a hit we
    return status=done immediately and do not re-run OCR. Pass force=True
    to bypass the cache.

    Default scan_all=False finds only the first dialogue and stops;
    scan_all=True walks the whole video for every distinct line.
    """
    job_id = job_id_for(url, target_text, scan_all=scan_all)
    video_id = video_id_for(url)

    existing = redis_client.get_job_status(job_id)
    if existing and existing["status"] in (redis_client.STATUS_PENDING, redis_client.STATUS_PROCESSING):
        logger.info("Job %s already in flight, not re-submitting", job_id)
        return job_id

    if not force:
        cached = redis_client.get_cached_result(job_id)
        if cached is not None:
            try:
                if not _postgres_has_result(video_id, target_text, scan_all):
                    logger.info("Redis hit for %s but Postgres empty — restoring rows", job_id)
                    _persist_result(video_id, url, cached)
                logger.info("Cache hit (redis) for %s — skipping pipeline", job_id)
                _mark_cache_hit(job_id, video_id, "redis")
                return job_id
            except Exception:
                logger.exception("Could not restore Redis cache for %s — running pipeline", job_id)
        elif _postgres_has_result(video_id, target_text, scan_all):
            logger.info("Cache hit (postgres) for %s — skipping pipeline", job_id)
            _mark_cache_hit(job_id, video_id, "postgres")
            return job_id

    redis_client.set_job_status(
        job_id,
        redis_client.STATUS_PENDING,
        video_id=video_id,
        stage="queued",
        message="Queued…",
        progress=0.0,
        cached=False,
    )
    _executor.submit(_run_job, job_id, video_id, url, target_text, force, scan_all)
    return job_id


def _run_job(
    job_id: str,
    video_id: str,
    url: str,
    target_text: Optional[str],
    force: bool,
    scan_all: bool = False,
) -> None:
    redis_client.set_job_status(
        job_id,
        redis_client.STATUS_PROCESSING,
        video_id=video_id,
        stage="queued",
        message="Starting pipeline…",
        progress=0.0,
    )

    def on_progress(stage: str, message: str, progress=None) -> None:
        redis_client.set_job_status(
            job_id,
            redis_client.STATUS_PROCESSING,
            video_id=video_id,
            stage=stage,
            message=message,
            progress=progress,
        )

    try:
        result = process_video_full(
            url,
            target_text=target_text,
            force=force,
            scan_all=scan_all,
            on_progress=on_progress,
        )
        on_progress("save", "Persisting results…", 0.99)
        _persist_result(video_id, url, result)
        redis_client.cache_result(job_id, result)
        redis_client.set_job_status(
            job_id,
            redis_client.STATUS_DONE,
            video_id=video_id,
            stage="done",
            message="Finished",
            progress=1.0,
            cached=False,
        )
        logger.info(
            "Job %s done (%d dialogues, scan_all=%s)",
            job_id, len(result["dialogues"]), scan_all,
        )
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        redis_client.set_job_status(
            job_id,
            redis_client.STATUS_ERROR,
            video_id=video_id,
            error=str(exc),
            stage="error",
            message="Pipeline failed",
        )


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
