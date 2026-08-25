"""
Text detector interface.

Default implementation delegates to EasyOCR, whose detector is a DBNet
model under the hood -- matching the architecture diagram's "Text Detection
(DBNet Mobile)" stage without hand-rolling model loading/inference code.

Kept as a separate module (rather than baked into engine.py) so a
hand-trained/standalone DBNet checkpoint can be swapped in later by
implementing the same `detect()` interface.
"""
from __future__ import annotations

from typing import List, Protocol

import numpy as np

from core.sampling.roi_sampler import BBox


class TextDetector(Protocol):
    def detect(self, frame: np.ndarray) -> List[BBox]:
        """Return bounding boxes of text-like regions in `frame`."""
        ...
