"""
Engine/session setup, driven by POSTGRES_DSN (see .env.example).

Falls back to a local SQLite file when POSTGRES_DSN isn't set, so
`uvicorn service.main:app` is runnable for local dev/demo without standing
up Postgres first -- mirrors the same "degrade gracefully, don't hard-fail
on missing infra" approach core/config.py takes for ffmpeg.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from service.db.models import Base

_DEFAULT_SQLITE_DSN = "sqlite:///./outputs/frame_finder.db"

DSN = os.getenv("POSTGRES_DSN") or _DEFAULT_SQLITE_DSN

_engine_kwargs = {}
if DSN.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
    os.makedirs("./outputs", exist_ok=True)

engine = create_engine(DSN, **_engine_kwargs)
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
