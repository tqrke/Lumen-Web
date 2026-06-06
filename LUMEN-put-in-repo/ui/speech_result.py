"""Speech recognition result with confidence — gates command execution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpeechResult:
    text: str
    confidence: float
    source: str

    @property
    def ok(self) -> bool:
        return bool(self.text) and self.confidence >= 0.55

    @property
    def high(self) -> bool:
        return bool(self.text) and self.confidence >= 0.72
