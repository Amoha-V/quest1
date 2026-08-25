"""
OpenCV preprocessing to make on-screen text easier for the OCR engine to
pick up: denoise, boost contrast, and optionally crop to a known ROI.
"""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from core.sampling.roi_sampler import BBox


def preprocess(frame: np.ndarray, roi: Optional[BBox] = None) -> np.ndarray:
    img = frame
    if roi is not None:
        x, y, w, h = roi
        img = img[y : y + h, x : x + w]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contrasted = clahe.apply(denoised)

    # Back to 3-channel since most OCR models expect RGB/BGR input.
    return cv2.cvtColor(contrasted, cv2.COLOR_GRAY2BGR)
