"""
POST /videos/process        -> enqueue an (async) processing job for a url
                                (+ optional target dialogue), returns job_id
GET  /videos/{job_id}/status -> poll job status (Redis-backed)
GET  /videos/{video_id}/results -> persisted dialogues + target matches for
                                a video (Postgres-backed)

Wired to core.pipeline.process_video_full via
service/workers/video_worker.py (background thread pool) +
service/cache/redis_client.py for job status +
service/db for persisted results, per the architecture diagram.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.source.downloader import video_id_for
from service.cache import redis_client
from service.db.models import Dialogue, TargetMatch, Video
from service.db.session import get_session_dep
from service.storage import minio_client
from service.workers import video_worker

router = APIRouter()


class ProcessRequest(BaseModel):
    url: str
    target_text: Optional[str] = None
    force: bool = False
    # False (default): find the first dialogue and stop the pipeline.
    # True: scan the whole video and return every distinct dialogue frame.
    scan_all: bool = False


class ProcessResponse(BaseModel):
    job_id: str
    video_id: str
    status: str


@router.post("/process", response_model=ProcessResponse)
def process(req: ProcessRequest):
    if not req.url.strip():
        raise HTTPException(status_code=422, detail="url must not be empty")

    job_id = video_worker.submit_job(
        req.url,
        target_text=req.target_text,
        force=req.force,
        scan_all=req.scan_all,
    )
    job_status = redis_client.get_job_status(job_id)
    vid = job_status["video_id"] if job_status else video_id_for(req.url)
    return ProcessResponse(
        job_id=job_id,
        video_id=vid,
        status=job_status["status"] if job_status else "pending",
    )


@router.get("/{job_id}/status")
def status(job_id: str):
    job_status = redis_client.get_job_status(job_id)
    if job_status is None:
        raise HTTPException(status_code=404, detail=f"No job found for id {job_id!r}")
    return job_status


def _frame_url(stored_value: Optional[str]) -> Optional[str]:
    """stored_value is whatever service.storage.minio_client.upload_frame()
    returned (a "minio:<key>" or "local:<path>" string) -- resolve it to
    something the frontend can load an <img> from."""
    if not stored_value:
        return None
    bare = minio_client.strip_prefix(stored_value)
    if minio_client.is_object_key(stored_value):
        return minio_client.presigned_url(bare)
    return f"/static-local?path={bare}"


@router.get("/{video_id}/results")
def results(video_id: str, session: Session = Depends(get_session_dep)):
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail=f"No video found for id {video_id!r}")

    dialogues = (
        session.query(Dialogue)
        .filter(Dialogue.video_id == video_id)
        .order_by(Dialogue.timestamp_sec)
        .all()
    )
    target_matches = (
        session.query(TargetMatch)
        .filter(TargetMatch.video_id == video_id)
        .order_by(TargetMatch.created_at.desc())
        .all()
    )

    return {
        "video_id": video.id,
        "url": video.url,
        "status": video.status,
        "duration_sec": video.duration_sec,
        "fps": video.fps,
        "dialogues": [
            {
                "index": d.idx,
                "text": d.text,
                "timestamp_sec": d.timestamp_sec,
                "frame_number": d.frame_number,
                "confidence": d.confidence,
                "bbox": d.bbox,
                "frame_url": _frame_url(d.frame_object_key),
            }
            for d in dialogues
        ],
        "target_matches": [
            {
                "target_text": t.target_text,
                "matched": t.matched,
                "timestamp_sec": t.timestamp_sec,
                "frame_number": t.frame_number,
                "recognized_text": t.recognized_text,
                "similarity": t.similarity,
                "ocr_confidence": t.ocr_confidence,
                "bbox": t.bbox,
                "frame_url": _frame_url(t.frame_object_key),
            }
            for t in target_matches
        ],
    }
