"""
Fuzzy matching between OCR output and the target dialogue text.

Exact string equality is unrealistic for OCR (misread characters, stray
punctuation, casing differences), so we score similarity and accept above
a configurable threshold -- this is also how we quantify "ambiguous/
uncertain" results for the writeup: anything below threshold is reported
as a non-match rather than a low-confidence guess.
"""
from __future__ import annotations

from rapidfuzz import fuzz

from core.config import settings


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def similarity_score(candidate: str, target: str) -> float:
    """0.0-1.0 similarity between OCR candidate text and target dialogue."""
    return fuzz.token_sort_ratio(normalize(candidate), normalize(target)) / 100.0


def is_match(candidate: str, target: str) -> bool:
    return similarity_score(candidate, target) >= settings.text_similarity_threshold
