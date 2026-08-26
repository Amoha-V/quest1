"""
Groups matching detections that occur across consecutive/near timestamps
into a single "appearance event" and reports its earliest timestamp.

Needed because a coarse hit + backward refinement (roi_sampler.py) will
typically produce several timestamps all containing the same text -- we
want the *first* one, not just any one, and we want to be robust to a
single dropped/failed OCR read in the middle of the run.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TimestampHit:
    timestamp_sec: float
    text: str
    confidence: float
    similarity: float
    # None for ASR (spoken-dialogue) hits -- there's no on-screen region.
    bbox: Optional[tuple[int, int, int, int]] = None


def earliest_hit(hits: List[TimestampHit]) -> TimestampHit:
    """Given all matching hits found during backward refinement, return the
    one with the smallest timestamp -- i.e. the first frame the dialogue
    appears on."""
    if not hits:
        raise ValueError("earliest_hit() called with no hits")
    return min(hits, key=lambda h: h.timestamp_sec)
