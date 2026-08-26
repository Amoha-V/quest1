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
from core.sampling.roi_sampler import subtitle_band

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

    Calls reader.detect() then reader.recognize() -- exactly the two calls
    readtext() makes internally (see easyocr.Reader.readtext source) -- so a
    frame with zero detected text regions skips the (pricier) CRNN
    recognition pass instead of paying for it and discarding the empty
    result. Deliberately NOT calling reader.detect() followed by
    reader.readtext(): readtext() re-runs its own internal detect() pass,
    which would silently double the (expensive, ~1.8s/frame at typical
    subtitle-crop size on CPU) detection cost on every frame that *does*
    have text -- a real regression, not a speedup, measured while profiling
    this against a real video.
    """
    from easyocr.utils import reformat_input

    reader = _get_reader()
    img, img_cv_grey = reformat_input(frame)
    horizontal_list, free_list = reader.detect(img, reformat=False)
    horizontal_list, free_list = horizontal_list[0], free_list[0]
    if not horizontal_list and not free_list:
        return []

    raw_results = reader.recognize(img_cv_grey, horizontal_list, free_list, reformat=False)

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


def offset_detections(detections: List[OcrDetection], origin_x: int, origin_y: int) -> List[OcrDetection]:
    """Map crop-relative boxes back onto the full frame."""
    if origin_x == 0 and origin_y == 0:
        return detections
    out: List[OcrDetection] = []
    for d in detections:
        x, y, w, h = d.bbox
        out.append(
            OcrDetection(
                text=d.text,
                confidence=d.confidence,
                bbox=(x + origin_x, y + origin_y, w, h),
            )
        )
    return out


def run_dialogue_ocr(frame: np.ndarray) -> List[OcrDetection]:
    """OCR the subtitle band only, then map boxes back to full-frame coords."""
    from core.matching.text_filter import filter_detections
    from core.preprocessing.frame_preprocessor import preprocess

    h, w = frame.shape[:2]
    roi = subtitle_band(w, h)
    detections = filter_detections(run_ocr(preprocess(frame, roi=roi)))
    if roi is not None:
        detections = offset_detections(detections, roi[0], roi[1])
    return detections
