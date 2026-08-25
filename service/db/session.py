"""
Engine/session setup, driven by POSTGRES_DSN (see .env.example).

Falls back to a local SQLite file when POSTGRES_DSN isn't set *or* when
Postgres isn't reachable, so `uvicorn service.main:app` is runnable for
local dev/demo without standing up Postgres first -- mirrors the same
"degrade gracefully, don't hard-fail on missing infra" approach
core/config.py takes for ffmpeg.
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from service.db.models import Base

logger = logging.getLogger(__name__)

_DEFAULT_SQLITE_DSN = "sqlite:///./outputs/frame_finder.db"


def _build_engine(dsn: str):
    kwargs = {}
    if dsn.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        os.makedirs("./outputs", exist_ok=True)
    return create_engine(dsn, **kwargs)


def _resolve_engine():
    configured = (os.getenv("POSTGRES_DSN") or "").strip()
    if not configured:
        logger.info("POSTGRES_DSN not set -- using SQLite at %s", _DEFAULT_SQLITE_DSN)
        return _build_engine(_DEFAULT_SQLITE_DSN)

    # When POSTGRES_DSN is set, require Postgres (no silent SQLite fallback).
    engine = _build_engine(configured)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("Connected to Postgres via POSTGRES_DSN")
    return engine


engine = _resolve_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create tables if they don't exist yet. Safe to call repeatedly."""
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session_dep() -> Iterator[Session]:
    """FastAPI dependency variant (yields, doesn't need `with`)."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
