"""
FastAPI service around core/ -- the multi-video, searchable-history product
described in the architecture diagram. Not required for the assignment
itself (core/pipeline.py + cli.py already produce the required single-URL
output standalone); this is the additive demo layer.

Run with:
    uvicorn service.main:app --reload
Works out of the box for local dev even without Redis/Postgres/MinIO
running -- see the fallback behavior documented in service/cache/,
service/db/session.py, and service/storage/.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from core.config import settings as core_settings
from service.db.session import init_db
from service.routers import search, videos

app = FastAPI(title="Frame Finder", version="0.1.0")

_allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(videos.router, prefix="/videos", tags=["videos"])
app.include_router(search.router, tags=["search"])


@app.on_event("startup")
def _on_startup() -> None:
    init_db()
    core_settings.ensure_dirs()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/static-local")
def static_local(path: str):
    """
    Serves a frame image straight off local disk when MinIO isn't
    configured/reachable (see service/storage/minio_client.py's fallback).
    Restricted to core_settings.output_dir so this can't be used to read
    arbitrary files off the host.
    """
    from pathlib import Path

    output_root = core_settings.output_dir.resolve()
    requested = Path(path).resolve()
    try:
        requested.relative_to(output_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="path must be under the output directory")
    if not requested.is_file():
        raise HTTPException(status_code=404, detail="frame not found")
    return FileResponse(requested)
