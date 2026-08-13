"""Post-save residual detection with privacy-safe reporting."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from src.detector import DetectionEngine
from src.docx_processor import StoryKind, TextContainer
from src.models import PIIEntity, PIIType
from src.pseudonymizer import normalize_entity_text
from src.redaction_plan import PlannedReplacement


@dataclass(frozen=True, slots=True)
class ResidualFinding:
    container_id: str
    story_type: StoryKind
    entity: PIIEntity
    classification: str

    def safe_summary(self) -> dict[str, object]:
        return {
            "container_id": self.container_id,
            "story_type": self.story_type.value,
            "classification": self.classification,
            **self.entity.safe_summary(),
        }


@dataclass(frozen=True, slots=True)
class _SyntheticSpan:
    container_id: str
    start: int
    end: int


def _synthetic_output_spans(
    planned_replacements: tuple[PlannedReplacement, ...],
) -> tuple[_SyntheticSpan, ...]:
    grouped: dict[str, list[PlannedReplacement]] = {}
    for item in planned_replacements:
        grouped.setdefault(item.container_id, []).append(item)

    spans: list[_SyntheticSpan] = []
    for container_id, replacements in grouped.items():
        offset = 0
        for item in sorted(
            replacements,
            key=lambda candidate: (candidate.entity.start, candidate.entity.end),
        ):
            start = item.entity.start + offset
            end = start + len(item.replacement)
            spans.append(_SyntheticSpan(container_id, start, end))
            offset += len(item.replacement) - item.entity.span_length
    return tuple(spans)


@dataclass(frozen=True, slots=True)
class LeakScanReport:
    findings: tuple[ResidualFinding, ...]
    minimum_confidence: float

    @property
    def high_confidence_count(self) -> int:
        return len(self.findings)

    @property
    def known_synthetic_count(self) -> int:
        return self.exact_synthetic_count + self.synthetic_contained_count

    @property
    def exact_synthetic_count(self) -> int:
        return sum(
            item.classification == "EXACT_KNOWN_SYNTHETIC" for item in self.findings
        )

    @property
    def synthetic_contained_count(self) -> int:
        return sum(
            item.classification == "CONTAINED_IN_SYNTHETIC_REPLACEMENT"
            for item in self.findings
        )

    @property
    def broad_overlap_review_count(self) -> int:
        return sum(
            item.classification == "BROAD_OVERLAP_REVIEW" for item in self.findings
        )

    @property
    def unclassified_residual_count(self) -> int:
        return sum(item.classification == "UNCLASSIFIED" for item in self.findings)

    @property
    def review_required_count(self) -> int:
        return self.broad_overlap_review_count + self.unclassified_residual_count

    def to_dict(self) -> dict[str, object]:
        all_by_type = Counter(item.entity.entity_type.value for item in self.findings)
        unclassified_by_type = Counter(
            item.entity.entity_type.value
            for item in self.findings
            if item.classification == "UNCLASSIFIED"
        )
        review_by_type = Counter(
            item.entity.entity_type.value
            for item in self.findings
            if item.classification in {"BROAD_OVERLAP_REVIEW", "UNCLASSIFIED"}
        )
        return {
            "privacy_safe": True,
            "minimum_confidence": self.minimum_confidence,
            "high_confidence_detection_count": self.high_confidence_count,
            "known_synthetic_detection_count": self.known_synthetic_count,
            "exact_known_synthetic_detection_count": self.exact_synthetic_count,
            "synthetic_contained_detection_count": self.synthetic_contained_count,
            "broad_overlap_review_count": self.broad_overlap_review_count,
            "unclassified_residual_count": self.unclassified_residual_count,
            "review_required_count": self.review_required_count,
            "detections_by_type": dict(sorted(all_by_type.items())),
            "review_required_by_type": dict(sorted(review_by_type.items())),
            "unclassified_by_type": dict(sorted(unclassified_by_type.items())),
            "review_findings": [
                item.safe_summary()
                for item in self.findings
                if item.classification in {"BROAD_OVERLAP_REVIEW", "UNCLASSIFIED"}
            ],
            "interpretation": (
                "Known synthetic detections are expected because replacements "
                "remain realistic PII-shaped values. Broad-overlap and "
                "unclassified detections require review and are not claimed to "
                "be leaks without context."
            ),
        }


class LeakScanner:
    def __init__(self, detector: DetectionEngine, *, minimum_confidence: float = 0.85):
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between 0 and 1")
        self._detector = detector
        self._minimum_confidence = minimum_confidence

    def scan(self, extracted_redacted_text: str) -> LeakScanReport:
        findings = tuple(
            ResidualFinding(
                container_id="logical_text",
                story_type=StoryKind.BODY_PARAGRAPH,
                entity=entity,
                classification="UNCLASSIFIED",
            )
            for entity in self._detector.detect(extracted_redacted_text)
            if entity.confidence >= self._minimum_confidence
        )
        return LeakScanReport(
            findings=findings,
            minimum_confidence=self._minimum_confidence,
        )

    def scan_containers(
        self,
        containers: tuple[TextContainer, ...],
        *,
        planned_replacements: tuple[PlannedReplacement, ...] = (),
    ) -> LeakScanReport:
        """Scan each reopened container and classify known synthetic values."""

        synthetic_keys = {
            (
                item.entity.entity_type,
                normalize_entity_text(item.entity.entity_type, item.replacement),
            )
            for item in planned_replacements
        }
        synthetic_spans = _synthetic_output_spans(planned_replacements)
        findings: list[ResidualFinding] = []
        for container in containers:
            for entity in self._detector.detect(container.text):
                if entity.confidence < self._minimum_confidence:
                    continue
                key: tuple[PIIType, str] = (
                    entity.entity_type,
                    normalize_entity_text(entity.entity_type, entity.text),
                )
                if key in synthetic_keys:
                    classification = "EXACT_KNOWN_SYNTHETIC"
                elif any(
                    span.container_id == container.id
                    and span.start <= entity.start
                    and entity.end <= span.end
                    for span in synthetic_spans
                ):
                    classification = "CONTAINED_IN_SYNTHETIC_REPLACEMENT"
                elif any(
                    span.container_id == container.id
                    and entity.start < span.end
                    and span.start < entity.end
                    for span in synthetic_spans
                ):
                    classification = "BROAD_OVERLAP_REVIEW"
                else:
                    classification = "UNCLASSIFIED"
                findings.append(
                    ResidualFinding(
                        container_id=container.id,
                        story_type=container.story_type,
                        entity=entity,
                        classification=classification,
                    )
                )
        return LeakScanReport(
            findings=tuple(findings),
            minimum_confidence=self._minimum_confidence,
        )
