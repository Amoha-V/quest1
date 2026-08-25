"""
SQLAlchemy models: videos, dialogues, target_matches.

- Video: one row per processed video (keyed by the same video_id
  core.source.downloader.video_id_for() computes, so service/ and
  core/'s notion of "which video is this" never drifts apart).
- Dialogue: one row per distinct on-screen line found by
  core.dialogue_scan.scan_all_dialogues() for that video -- this is what
  backs "display ALL detected dialogues" + GET /videos/{id}/search.
- TargetMatch: one row per (video, target_text) lookup via
  core.resolver.resolve() -- kept separate from Dialogue because a target
  lookup is frame-accurate (backward-refined) while a Dialogue's timestamp
  is only coarse-interval-accurate (see core/dialogue_scan.py docstring).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(12), primary_key=True)  # video_id_for(url)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/processing/done/error
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    dialogues: Mapped[list["Dialogue"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    target_matches: Mapped[list["TargetMatch"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class Dialogue(Base):
    __tablename__ = "dialogues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), nullable=False, index=True)
    idx: Mapped[int] = mapped_column(Integer, nullable=False)  # order within the video
    text: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp_sec: Mapped[float] = mapped_column(Float, nullable=False)
    frame_number: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    bbox: Mapped[dict] = mapped_column(JSON, nullable=True)
    frame_object_key: Mapped[str] = mapped_column(Text, nullable=False)  # MinIO key or local path

    video: Mapped["Video"] = relationship(back_populates="dialogues")


class TargetMatch(Base):
    __tablename__ = "target_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), nullable=False, index=True)
    target_text: Mapped[str] = mapped_column(Text, nullable=False)
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    timestamp_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    frame_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recognized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox: Mapped[dict] = mapped_column(JSON, nullable=True)
    frame_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    video: Mapped["Video"] = relationship(back_populates="target_matches")
