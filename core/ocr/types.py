from __future__ import annotations

from dataclasses import dataclass

from core.sampling.roi_sampler import BBox


@dataclass
class OcrDetection:
    text: str
    confidence: float
    bbox: BBox
