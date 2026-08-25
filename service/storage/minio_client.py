"""
MinIO client for persisting extracted frame images at scale, replacing the
local outputs/ dir core.pipeline uses for the CLI/demo path.

Degrades gracefully (same pattern as service/cache/redis_client.py and
service/db/session.py): if MinIO isn't reachable, upload_frame() logs a
warning and returns the local file path unchanged, so
GET /videos/{id}/results can still serve frames straight off disk via
service/main.py's static file mount in local dev without standing up
MinIO first. In that mode `object_key` returned == the local path passed
in, and service/routers can tell the two apart by checking
`is_object_key()`.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "frame-finder-frames")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

_client = None
_bucket_ready = False


def _get_client():
    global _client, _bucket_ready
    if _client is None:
        try:
            from minio import Minio

            _client = Minio(
                MINIO_ENDPOINT,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=MINIO_SECURE,
            )
            if not _client.bucket_exists(MINIO_BUCKET):
                _client.make_bucket(MINIO_BUCKET)
            _bucket_ready = True
            logger.info("Connected to MinIO at %s (bucket=%s)", MINIO_ENDPOINT, MINIO_BUCKET)
        except Exception as exc:  # pragma: no cover - infra-dependent
            logger.warning("MinIO unavailable (%s) -- frames will stay on local disk", exc)
            _client = False  # sentinel: "tried, unavailable" (falsy but not None)
    return _client if _client else None


_MINIO_PREFIX = "minio:"
_LOCAL_PREFIX = "local:"


def is_object_key(value: str) -> bool:
    """True if `value` (as stored by upload_frame) is a real MinIO object
    key rather than a local-disk fallback path (used by routers deciding
    whether to build a presigned URL or just serve a local file)."""
    return value.startswith(_MINIO_PREFIX)


def upload_frame(local_path: Path, object_key: str) -> str:
    """
    Upload the frame at `local_path` to MinIO under `object_key`.
    Returns "minio:<object_key>" on success, or "local:<local_path>" if
    MinIO isn't available -- callers store whatever comes back verbatim
    and use is_object_key() / strip_prefix() to resolve it later. The
    explicit prefix (rather than guessing from path shape) is what makes
    that resolution unambiguous.
    """
    client = _get_client()
    if client is None:
        return f"{_LOCAL_PREFIX}{local_path}"

    try:
        client.fput_object(MINIO_BUCKET, object_key, str(local_path), content_type="image/png")
        return f"{_MINIO_PREFIX}{object_key}"
    except Exception as exc:  # pragma: no cover - infra-dependent
        logger.warning("MinIO upload failed for %s (%s) -- keeping local path", local_path, exc)
        return f"{_LOCAL_PREFIX}{local_path}"


def strip_prefix(value: str) -> str:
    """Strip the minio:/local: prefix upload_frame() adds, returning the
    bare object key or filesystem path underneath."""
    for prefix in (_MINIO_PREFIX, _LOCAL_PREFIX):
        if value.startswith(prefix):
            return value[len(prefix):]
    return value


def presigned_url(object_key: str, expires_sec: int = 3600) -> Optional[str]:
    client = _get_client()
    if client is None:
        return None
    try:
        from datetime import timedelta

        return client.presigned_get_object(
            MINIO_BUCKET, object_key, expires=timedelta(seconds=expires_sec)
        )
    except Exception as exc:  # pragma: no cover - infra-dependent
        logger.warning("MinIO presigned URL failed for %s (%s)", object_key, exc)
        return None
