"""Post-save residual detection with privacy-safe reporting."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from src.detector import DetectionEngine
from src.models import PIIEntity


@dataclass(frozen=True, slots=True)
class LeakScanReport:
    residuals: tuple[PIIEntity, ...]

    @property
    def high_confidence_count(self) -> int:
        return len(self.residuals)

    def to_dict(self) -> dict[str, object]:
        by_type = Counter(entity.entity_type.value for entity in self.residuals)
        return {
            "high_confidence_count": self.high_confidence_count,
            "by_type": dict(sorted(by_type.items())),
            "residuals": [entity.safe_summary() for entity in self.residuals],
        }


class LeakScanner:
    def __init__(self, detector: DetectionEngine, *, minimum_confidence: float = 0.85):
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between 0 and 1")
        self._detector = detector
        self._minimum_confidence = minimum_confidence

    def scan(self, extracted_redacted_text: str) -> LeakScanReport:
        residuals = tuple(
            entity
            for entity in self._detector.detect(extracted_redacted_text)
            if entity.confidence >= self._minimum_confidence
        )
        return LeakScanReport(residuals=residuals)
