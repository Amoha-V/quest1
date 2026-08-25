"""Filters raw OCR detections down to plausible dialogue-text candidates."""
from __future__ import annotations

import re
from typing import List

from core.ocr.types import OcrDetection

_MIN_ALPHA_CHARS = 3


def is_plausible_dialogue_text(text: str) -> bool:
    """Reject OCR noise: empty strings, pure symbols/numbers, single chars."""
    alpha_count = len(re.findall(r"[A-Za-z]", text))
    return alpha_count >= _MIN_ALPHA_CHARS


def filter_detections(detections: List[OcrDetection]) -> List[OcrDetection]:
    return [d for d in detections if is_plausible_dialogue_text(d.text)]
