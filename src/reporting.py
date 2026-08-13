"""Privacy-safe structured-detection reporting for DOCX containers."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from src import __version__
from src.detector import DetectionEngine
from src.docx_processor import (
    EXTRACTOR_SCHEMA_VERSION,
    StoryKind,
    TextContainer,
    extract_text_containers,
)
from src.models import PIIEntity, PIIType
from src.recognizers import all_recognizers


REPORT_TYPES = tuple(PIIType)


@dataclass(frozen=True, slots=True)
class ContainerDetection:
    container_id: str
    story_type: StoryKind
    entity: PIIEntity
    affected_run_count: int

    def to_dict(self, *, unsafe_show_pii: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "container_id": self.container_id,
            "story_type": self.story_type.value,
            **self.entity.safe_summary(),
            "affected_run_count": self.affected_run_count,
        }
        if unsafe_show_pii:
            result["text"] = self.entity.text
        return result


@dataclass(frozen=True, slots=True)
class DetectionReport:
    source_name: str
    source_sha256: str | None
    container_counts: dict[StoryKind, int]
    detections: tuple[ContainerDetection, ...]

    def summary(self) -> dict[str, object]:
        by_type: dict[PIIType, list[ContainerDetection]] = defaultdict(list)
        for detection in self.detections:
            by_type[detection.entity.entity_type].append(detection)

        return {
            "report_schema_version": "1.0",
            "tool_version": __version__,
            "extractor_schema_version": EXTRACTOR_SCHEMA_VERSION,
            "source_name": self.source_name,
            "source_sha256": self.source_sha256,
            "privacy_safe": True,
            "container_count": sum(self.container_counts.values()),
            "containers_by_story": {
                story.value: self.container_counts.get(story, 0) for story in StoryKind
            },
            "accepted_detection_count": len(self.detections),
            "detections_by_type": {
                entity_type.value: {
                    "accepted": len(items),
                    "cross_run": sum(item.affected_run_count > 1 for item in items),
                    "average_confidence": (
                        round(
                            sum(item.entity.confidence for item in items) / len(items),
                            4,
                        )
                        if items
                        else None
                    ),
                }
                for entity_type in REPORT_TYPES
                for items in (by_type[entity_type],)
            },
        }

    def to_dict(self, *, unsafe_show_pii: bool = False) -> dict[str, object]:
        result = self.summary()
        if unsafe_show_pii:
            result["privacy_safe"] = False
            result["warning"] = "Unsafe output contains document PII"
            result["detections"] = [
                item.to_dict(unsafe_show_pii=True) for item in self.detections
            ]
        return result


def detect_containers(
    containers: tuple[TextContainer, ...],
    *,
    engine: DetectionEngine | None = None,
    source_name: str = "document.docx",
    source_sha256: str | None = None,
) -> DetectionReport:
    detector = engine or DetectionEngine(all_recognizers())
    records: list[ContainerDetection] = []
    for container in containers:
        for entity in detector.detect(container.text):
            records.append(
                ContainerDetection(
                    container_id=container.id,
                    story_type=container.story_type,
                    entity=entity,
                    affected_run_count=len(
                        container.logical.map_span(entity.start, entity.end)
                    ),
                )
            )
    records.sort(
        key=lambda item: (
            item.container_id,
            item.entity.start,
            item.entity.end,
            item.entity.entity_type.value,
        )
    )
    return DetectionReport(
        source_name=source_name,
        source_sha256=source_sha256,
        container_counts=dict(Counter(item.story_type for item in containers)),
        detections=tuple(records),
    )


def detect_docx(path: Path | str) -> DetectionReport:
    source_path = Path(path)
    containers = extract_text_containers(source_path)
    digest = sha256()
    with source_path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return detect_containers(
        containers,
        source_name=source_path.name,
        source_sha256=digest.hexdigest(),
    )
