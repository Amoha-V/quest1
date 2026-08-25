"""
Thin Redis wrapper used for two things (per the architecture diagram):

  1. Job status, so POST /videos/process can return immediately and
     GET /videos/{id}/status can be polled while
     service/workers/video_worker.py runs the pipeline in the background.
  2. The "CACHE CHECK" step before a full re-process: a finished job's
     full API response is cached under its job key so an identical
     (url, target_text) request short-circuits straight to Redis instead
     of re-running OCR (core.pipeline already does its own flat-file
     result cache too, at the pipeline layer -- this is the same idea one
     layer up, so the service can skip even the download/probe step).

Degrades gracefully to an in-process dict if Redis isn't reachable, so the
service is runnable for local dev/demo without standing up Redis first
(same pattern as service/db/session.py's SQLite fallback). In multi-worker
deployments this fallback isn't shared across processes -- set REDIS_URL
and run Redis for that.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
JOB_STATUS_TTL_SEC = 60 * 60 * 6  # 6h
RESULT_CACHE_TTL_SEC = 60 * 60 * 24 * 7  # 7d

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_ERROR = "error"


class _InMemoryFallback:
    """Minimal (key -> (value, expires_at)) store with the redis-py surface
    this module actually uses, so callers don't need to know which backend
    is active."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, Optional[float]]] = {}
        self._lock = threading.Lock()

    def set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        expires_at = time.time() + ex if ex else None
        with self._lock:
            self._data[key] = (value, expires_at)

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at is not None and time.time() > expires_at:
                del self._data[key]
                return None
            return value

    def ping(self) -> bool:
        return True


def _make_client():
    try:
        import redis

        client = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=1)
        client.ping()
        logger.info("Connected to Redis at %s", REDIS_URL)
        return client
    except Exception as exc:  # pragma: no cover - infra-dependent
        logger.warning("Redis unavailable (%s) -- falling back to in-memory job store", exc)
        return _InMemoryFallback()


_client = None
_client_lock = threading.Lock()


def _get_client():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = _make_client()
    return _client


def _status_key(job_id: str) -> str:
    return f"frame-finder:job:{job_id}:status"


def _result_key(job_id: str) -> str:
    return f"frame-finder:job:{job_id}:result"


def set_job_status(
    job_id: str,
    status: str,
    *,
    video_id: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    payload = {"job_id": job_id, "status": status, "video_id": video_id, "error": error}
    _get_client().set(_status_key(job_id), json.dumps(payload), ex=JOB_STATUS_TTL_SEC)


def get_job_status(job_id: str) -> Optional[dict[str, Any]]:
    raw = _get_client().get(_status_key(job_id))
    return json.loads(raw) if raw else None


def cache_result(job_id: str, result: dict[str, Any]) -> None:
    _get_client().set(_result_key(job_id), json.dumps(result), ex=RESULT_CACHE_TTL_SEC)


def get_cached_result(job_id: str) -> Optional[dict[str, Any]]:
    raw = _get_client().get(_result_key(job_id))
    return json.loads(raw) if raw else None
