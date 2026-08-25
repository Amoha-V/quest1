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
from core.dialogue_scan import DialogueOccurrence, scan_all_dialogues
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

    result: ResolveResult = resolve(video_path, meta, target_text)

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


def process_video_full(url: str, target_text: Optional[str] = None, force: bool = False) -> dict:
    """
    Service-layer entrypoint: downloads/probes once, then

      1. always runs core.dialogue_scan.scan_all_dialogues() to collect
         *every* distinct dialogue line detected in the video (for the
         "display ALL detected dialogues" + search/filter UI feature), and
      2. if `target_text` is given, additionally runs core.resolver.resolve()
         for a frame-accurate answer on that specific line (same logic
         cli.py/process_video uses), since scan_all_dialogues() only
         resolves each line down to coarse-interval precision.

    Distinct from process_video(): that one is the CLI/MVP path (single
    target, no full-video dialogue list). This one is what
    service/workers/video_worker.py calls. Both call into the same
    lower-level modules -- neither re-implements OCR/matching/sampling.
    """
    settings.ensure_dirs()
    video_id = video_id_for(url)
    run_dir = settings.output_dir / video_id
    manifest_path = run_dir / "dialogues" / "manifest.json"

    video_path = download_video(url)
    meta: VideoMetadata = probe(video_path)
    logger.info(
        "Video metadata: duration=%.2fs fps=%.2f resolution=%dx%d",
        meta.duration_sec, meta.fps, meta.width, meta.height,
    )

    if manifest_path.exists() and not force:
        logger.info("Cache hit for dialogue scan of %s -> %s", url, manifest_path)
        dialogues_out = json.loads(manifest_path.read_text())
    else:
        dialogues: list[DialogueOccurrence] = scan_all_dialogues(video_path, meta)
        dialogues_dir = run_dir / "dialogues"
        dialogues_dir.mkdir(parents=True, exist_ok=True)
        dialogues_out = []
        for i, d in enumerate(dialogues):
            frame = extract_frame(video_path, d.first_timestamp_sec, meta)
            frame_path = dialogues_dir / f"{i:04d}.png"
            save_frame(frame, frame_path)
            dialogues_out.append(
                {
                    "index": i,
                    "text": d.text,
                    "timestamp_sec": d.first_timestamp_sec,
                    "timestamp": _format_timestamp(d.first_timestamp_sec),
                    "frame_number": d.frame_number,
                    "confidence": round(d.confidence, 4),
                    "bbox": d.bbox,
                    "frame_image_path": str(frame_path),
                }
            )
        manifest_path.write_text(json.dumps(dialogues_out, indent=2))

    output = {
        "url": url,
        "video_id": video_id,
        "duration_sec": meta.duration_sec,
        "fps": meta.fps,
        "dialogues": dialogues_out,
        "target_match": None,
    }

    if target_text:
        result: ResolveResult = resolve(video_path, meta, target_text)
        target_out = {"target_text": target_text, "matched": result.matched}
        if result.matched:
            _, frame_path, target_run_dir = _result_paths(video_id, target_text)
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
        output["target_match"] = target_out

    return output


def _format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"
