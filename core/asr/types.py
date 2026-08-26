from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TranscriptSegment:
    text: str
    start_sec: float
    end_sec: float
    avg_logprob: float = 0.0
