"""
Top-level orchestrator: video URL + target dialogue -> full result.

This is the single entrypoint both cli.py and service/workers/video_worker.py
call into -- neither of them re-implements pipeline logic, they just choose
how to trigger it and what to do with the result.

Includes simple flat-file result caching (JSON) keyed by video_id so
re-running the same URL doesn't redo the (expensive) OCR scan. This is
separate from -- and doesn't require -- the service layer's Redis/Postgres
cache, which exists for cross-video search rather than single-run reuse.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from core.config import settings
from core.dialogue_scan import DialogueOccurrence, scan_all_dialogues, scan_first_dialogue
from core.extraction.frame_extractor import extract_frame, save_frame
from core.resolver import ResolveResult, resolve
from core.source.downloader import download_video, video_id_for
from core.source.metadata import VideoMetadata, probe

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


def _result_paths(video_id: str, target_text: str) -> tuple[Path, Path, Path]:
    # scope by video_id AND target text, since the same video may be queried
    # for different dialogues.
    import hashlib

    text_key = hashlib.sha1(target_text.encode("utf-8")).hexdigest()[:8]
    run_dir = settings.output_dir / video_id / text_key
    return run_dir / "result.json", run_dir / "frame.png", run_dir


def process_video(url: str, target_text: str, force: bool = False) -> dict:
    """
    Run the full pipeline for `url` looking for `target_text`.
    Returns a JSON-serializable dict (also written to outputs/<id>/result.json).

    Default assignment path: finds the *first* appearance of the target
    dialogue and stops (resolver stop_at_first=True).
    """
    settings.ensure_dirs()
    video_id = video_id_for(url)
    result_path, frame_path, run_dir = _result_paths(video_id, target_text)

    if result_path.exists() and not force:
        logger.info("Cache hit for %s / %r -> %s", url, target_text, result_path)
        return json.loads(result_path.read_text())

    video_path = download_video(url)
    meta: VideoMetadata = probe(video_path)
    logger.info(
        "Video metadata: duration=%.2fs fps=%.2f resolution=%dx%d",
        meta.duration_sec, meta.fps, meta.width, meta.height,
    )

    result: ResolveResult = resolve(video_path, meta, target_text, stop_at_first=True)

    output = {
        "url": url,
        "video_id": video_id,
        "target_text": result.target_text,
        "matched": result.matched,
    }

    if result.matched:
        frame = extract_frame(video_path, result.timestamp_sec, meta)
        save_frame(frame, frame_path)
        output.update(
            {
                "timestamp_sec": result.timestamp_sec,
                "timestamp": _format_timestamp(result.timestamp_sec),
                "frame_number": result.frame_number,
                "recognized_text": result.recognized_text,
                "similarity": round(result.similarity, 4),
                "ocr_confidence": round(result.ocr_confidence, 4),
                "bbox": result.bbox,
                "frame_image_path": str(frame_path),
                "other_matches": [asdict(h) for h in result.other_matches],
            }
        )
    else:
        output["best_near_miss"] = asdict(result.best_near_miss) if result.best_near_miss else None
        output["frame_image_path"] = None

    run_dir.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(output, indent=2))
    logger.info("Result written to %s", result_path)
    return output


def _dialogue_entry(
    index: int,
    text: str,
    timestamp_sec: float,
    frame_number: int,
    confidence: float,
    bbox,
    frame_path: Path,
) -> dict:
    return {
        "index": index,
        "text": text,
        "timestamp_sec": timestamp_sec,
        "timestamp": _format_timestamp(timestamp_sec),
        "frame_number": frame_number,
        "confidence": round(confidence, 4),
        "bbox": bbox,
        "frame_image_path": str(frame_path),
    }


def _target_match_out(
    video_id: str,
    video_path: Path,
    meta: VideoMetadata,
    target_text: str,
    result: ResolveResult,
) -> dict:
    target_out = {"target_text": target_text, "matched": result.matched}
    if result.matched:
        _, frame_path, _ = _result_paths(video_id, target_text)
        frame = extract_frame(video_path, result.timestamp_sec, meta)
        save_frame(frame, frame_path)
        target_out.update(
            {
                "timestamp_sec": result.timestamp_sec,
                "timestamp": _format_timestamp(result.timestamp_sec),
                "frame_number": result.frame_number,
                "recognized_text": result.recognized_text,
                "similarity": round(result.similarity, 4),
                "ocr_confidence": round(result.ocr_confidence, 4),
                "bbox": result.bbox,
                "frame_image_path": str(frame_path),
            }
        )
    return target_out


def process_video_full(
    url: str,
    target_text: Optional[str] = None,
    force: bool = False,
    scan_all: bool = False,
    on_progress=None,
) -> dict:
    """
    Service-layer entrypoint: downloads/probes once, then

      Default (scan_all=False):
        Find the first on-screen dialogue (or the given target_text) and
        stop. Refines to the exact onset frame via resolver. Returns that
        single answer in target_match (+ a one-item dialogues list).

      Optional (scan_all=True):
        Walk the whole video via scan_all_dialogues() for the "show every
        dialogue frame" UI, and if target_text is set also run a
        frame-accurate resolve for that line.

    `on_progress(stage, message, progress)` reports high-level stages for the UI.
    """
    def report(stage: str, message: str, progress: Optional[float] = None) -> None:
        if on_progress is not None:
            on_progress(stage, message, progress)

    settings.ensure_dirs()
    video_id = video_id_for(url)
    run_dir = settings.output_dir / video_id
    dialogues_dir = run_dir / "dialogues"
    manifest_path = dialogues_dir / ("manifest_all.json" if scan_all else "manifest_first.json")

    report("download", "Downloading video…", 0.02)
    video_path = download_video(url)
    report("probe", "Reading video metadata…", 0.08)
    meta: VideoMetadata = probe(video_path)
    logger.info(
        "Video metadata: duration=%.2fs fps=%.2f resolution=%dx%d (scan_all=%s)",
        meta.duration_sec, meta.fps, meta.width, meta.height, scan_all,
    )

    dialogues_out: list[dict] = []
    target_match = None

    if scan_all:
        if manifest_path.exists() and not force:
            logger.info("Cache hit for full dialogue scan of %s -> %s", url, manifest_path)
            report("scan", "Loading cached dialogue list…", 0.7)
            dialogues_out = json.loads(manifest_path.read_text())
        else:
            dialogues: list[DialogueOccurrence] = scan_all_dialogues(
                video_path, meta, on_progress=on_progress
            )
            report("save", "Saving dialogue frames…", 0.92)
            dialogues_dir.mkdir(parents=True, exist_ok=True)
            dialogues_out = []
            for i, d in enumerate(dialogues):
                frame = extract_frame(video_path, d.first_timestamp_sec, meta)
                frame_path = dialogues_dir / f"{i:04d}.png"
                save_frame(frame, frame_path)
                dialogues_out.append(
                    _dialogue_entry(
                        i, d.text, d.first_timestamp_sec, d.frame_number,
                        d.confidence, d.bbox, frame_path,
                    )
                )
            manifest_path.write_text(json.dumps(dialogues_out, indent=2))

        if target_text:
            result = resolve(
                video_path, meta, target_text, stop_at_first=True, on_progress=on_progress
            )
            target_match = _target_match_out(video_id, video_path, meta, target_text, result)
    else:
        # Default: first dialogue only, then stop.
        resolve_text = target_text
        if not resolve_text:
            first = scan_first_dialogue(video_path, meta, on_progress=on_progress)
            if first is None:
                logger.info("No dialogue found; returning empty result")
                report("save", "No dialogue found", 1.0)
                return {
                    "url": url,
                    "video_id": video_id,
                    "duration_sec": meta.duration_sec,
                    "fps": meta.fps,
                    "scan_all": False,
                    "dialogues": [],
                    "target_match": None,
                }
            resolve_text = first.text

        result = resolve(
            video_path, meta, resolve_text, stop_at_first=True, on_progress=on_progress
        )
        report("save", "Saving result frame…", 0.98)
        target_match = _target_match_out(video_id, video_path, meta, resolve_text, result)

        if result.matched:
            dialogues_dir.mkdir(parents=True, exist_ok=True)
            frame_path = Path(target_match["frame_image_path"])
            # Prefer a dialogues/ copy so the list UI can load a stable path.
            list_frame = dialogues_dir / "0000.png"
            if frame_path.exists():
                list_frame.write_bytes(frame_path.read_bytes())
            dialogues_out = [
                _dialogue_entry(
                    0,
                    result.recognized_text or resolve_text,
                    result.timestamp_sec,
                    result.frame_number,
                    result.ocr_confidence or 0.0,
                    result.bbox,
                    list_frame if list_frame.exists() else frame_path,
                )
            ]
            if not force:
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_text(json.dumps(dialogues_out, indent=2))

    report("done", "Finished", 1.0)
    return {
        "url": url,
        "video_id": video_id,
        "duration_sec": meta.duration_sec,
        "fps": meta.fps,
        "scan_all": scan_all,
        "dialogues": dialogues_out,
        "target_match": target_match,
    }


def _format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"
