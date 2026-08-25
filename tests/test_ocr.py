"""
Smoke test for the OCR engine against a synthetic frame with rendered text.

Marked slow: first run downloads EasyOCR's DBNet+CRNN weights (~100MB) and
loading them takes several seconds. Run explicitly with:
    pytest tests/test_ocr.py -m slow
"""
import cv2
import numpy as np
import pytest

from core.matching.similarity import is_match
from core.matching.text_filter import filter_detections
from core.ocr.engine import run_ocr


def _synthetic_text_frame(text: str) -> np.ndarray:
    frame = np.full((200, 800, 3), 255, dtype=np.uint8)
    cv2.putText(frame, text, (30, 110), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
    return frame


@pytest.mark.slow
def test_ocr_reads_synthetic_text():
    frame = _synthetic_text_frame("My mind rebels at stagnation")
    detections = filter_detections(run_ocr(frame))
    assert detections, "expected at least one text detection"
    assert any(
        is_match(d.text, "My mind rebels at stagnation") for d in detections
    ), f"no detection matched target, got: {[d.text for d in detections]}"
