"""
Text recognizer interface -- mirrors detector.py. Default engine (engine.py)
uses EasyOCR's CRNN-style recognizer under the hood, matching the
architecture diagram's "Text Recognition (CRNN Mobile)" stage.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np


class TextRecognizer(Protocol):
    def recognize(self, cropped_region: np.ndarray) -> tuple[str, float]:
        """Return (text, confidence) for a cropped text-region image."""
        ...
