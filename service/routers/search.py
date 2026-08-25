"""
GET /videos/{video_id}/search?q=... -- queries Postgres for OCR'd dialogues
matching q, across *all* detections stored for a video (not just the
target dialogue), per the frontend's "search/filter dialogues" feature.

Ranking reuses core.matching.similarity (the same fuzzy-match module the
core pipeline uses for target-text matching) rather than re-implementing
string similarity here, so "close enough" search results behave
consistently with how the pipeline itself decides on-screen text matches.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.matching.similarity import similarity_score
from service.db.models import Dialogue, Video
from service.db.session import get_session_dep

router = APIRouter()

_MIN_SEARCH_SIMILARITY = 0.3  # looser than pipeline matching -- this is fuzzy *search*, not a match decision


@router.get("/videos/{video_id}/search")
def search(video_id: str, q: str, session: Session = Depends(get_session_dep)):
    if session.get(Video, video_id) is None:
        raise HTTPException(status_code=404, detail=f"No video found for id {video_id!r}")

    q = q.strip()
    if not q:
        return {"query": q, "results": []}

    # Cheap substring pre-filter in SQL, then rank the (small, per-video)
    # candidate set with fuzzy similarity for typo/OCR-noise tolerance.
    substring_hits = (
        session.query(Dialogue)
        .filter(Dialogue.video_id == video_id, func.lower(Dialogue.text).contains(q.lower()))
        .all()
    )
    substring_ids = {d.id for d in substring_hits}

    all_dialogues = session.query(Dialogue).filter(Dialogue.video_id == video_id).all()

    scored = []
    for d in all_dialogues:
        score = 1.0 if d.id in substring_ids else similarity_score(d.text, q)
        if d.id in substring_ids or score >= _MIN_SEARCH_SIMILARITY:
            scored.append((score, d))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    return {
        "query": q,
        "results": [
            {
                "index": d.idx,
                "text": d.text,
                "timestamp_sec": d.timestamp_sec,
                "frame_number": d.frame_number,
                "confidence": d.confidence,
                "relevance": round(score, 4),
            }
            for score, d in scored
        ],
    }
