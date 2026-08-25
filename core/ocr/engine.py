"""
Orchestrates detection + recognition into a single call. This is the only
module the rest of the pipeline (resolver.py) talks to -- it doesn't care
whether detection/recognition are EasyOCR, PaddleOCR, or custom DBNet/CRNN
checkpoints underneath.
"""
from __future__ import annotations

import logging
import threading
from typing import List

import numpy as np

from core.config import settings
from core.ocr.types import OcrDetection

logger = logging.getLogger(__name__)

_reader = None
_reader_lock = threading.Lock()


def _get_reader():
    """Lazily instantiate the EasyOCR reader (loads DBNet+CRNN weights once,
    reused across calls -- model load is the expensive part)."""
    global _reader
    if _reader is None:
        with _reader_lock:
            if _reader is None:
                import easyocr

                logger.info("Loading EasyOCR (DBNet detector + CRNN recognizer) ...")
                _reader = easyocr.Reader(["en"], gpu=False)
    return _reader


def run_ocr(frame: np.ndarray) -> List[OcrDetection]:
    """
    Run detection + recognition on a full (or cropped) frame.
    Returns all detections above settings.ocr_min_confidence.
    """
    reader = _get_reader()
    raw_results = reader.readtext(frame)  # [(bbox_points, text, conf), ...]

    detections: List[OcrDetection] = []
    for bbox_points, text, conf in raw_results:
        if conf < settings.ocr_min_confidence:
            continue
        xs = [p[0] for p in bbox_points]
        ys = [p[1] for p in bbox_points]
        x, y = int(min(xs)), int(min(ys))
        w, h = int(max(xs) - x), int(max(ys) - y)
        detections.append(OcrDetection(text=text.strip(), confidence=float(conf), bbox=(x, y, w, h)))

    return detections
