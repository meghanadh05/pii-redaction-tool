"""Load and validate privacy-minimized, container-level ground truth."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import cast

from evaluation.evaluate import SpanAnnotation
from src.docx_processor import EXTRACTOR_SCHEMA_VERSION, extract_text_containers
from src.models import PIIType


@dataclass(frozen=True, slots=True)
class ReviewedContainer:
    container_id: str
    sample_stratum: str


@dataclass(frozen=True, slots=True)
class GroundTruthDataset:
    document_sha256: str
    extraction_version: str
    containers: tuple[ReviewedContainer, ...]
    annotations: tuple[SpanAnnotation, ...]

    @property
    def container_ids(self) -> frozenset[str]:
        return frozenset(item.container_id for item in self.containers)

    def distribution(self) -> dict[str, dict[str, int] | int]:
        return {
            "reviewed_container_count": len(self.containers),
            "annotation_count": len(self.annotations),
            "containers_by_stratum": dict(
                sorted(Counter(item.sample_stratum for item in self.containers).items())
            ),
            "annotations_by_type": {
                entity_type.value: sum(
                    item.entity_type is entity_type for item in self.annotations
                )
                for entity_type in PIIType
            },
        }


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_ground_truth(
    dataset_directory: Path | str,
    *,
    source_path: Path | str,
) -> GroundTruthDataset:
    """Load a completed dataset and validate every span against its source."""

    directory = Path(dataset_directory)
    source = Path(source_path)
    manifest = cast(
        dict[str, object],
        json.loads((directory / "manifest.json").read_text(encoding="utf-8")),
    )
    if manifest.get("annotation_status") != "complete":
        raise ValueError("Ground-truth annotation_status must be complete")
    document_sha256 = str(manifest.get("document_sha256", ""))
    if document_sha256 != _file_sha256(source):
        raise ValueError("Ground-truth source hash does not match the DOCX")
    extraction_version = str(manifest.get("extraction_version", ""))
    if extraction_version != EXTRACTOR_SCHEMA_VERSION:
        raise ValueError("Ground-truth extraction version is incompatible")

    raw_containers = manifest.get("containers")
    if not isinstance(raw_containers, list):
        raise ValueError("Ground-truth manifest containers must be a list")
    reviewed: list[ReviewedContainer] = []
    for raw_item in raw_containers:
        if (
            not isinstance(raw_item, dict)
            or raw_item.get("review_complete") is not True
        ):
            raise ValueError("Every selected container must be completely reviewed")
        container_id = raw_item.get("container_id")
        sample_stratum = raw_item.get("sample_stratum")
        if not isinstance(container_id, str) or not container_id:
            raise ValueError("Reviewed container ID must be non-empty")
        if not isinstance(sample_stratum, str) or not sample_stratum:
            raise ValueError("Reviewed container stratum must be non-empty")
        reviewed.append(ReviewedContainer(container_id, sample_stratum))
    reviewed_ids = [item.container_id for item in reviewed]
    if len(reviewed_ids) != len(set(reviewed_ids)):
        raise ValueError("Ground-truth manifest contains duplicate container IDs")

    source_containers = {item.id: item for item in extract_text_containers(source)}
    missing = set(reviewed_ids) - source_containers.keys()
    if missing:
        raise ValueError(f"Ground truth refers to {len(missing)} missing containers")

    annotations: list[SpanAnnotation] = []
    annotation_path = directory / "annotations.jsonl"
    for line_number, line in enumerate(
        annotation_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise ValueError(f"Annotation line {line_number} must be an object")
        try:
            annotation = SpanAnnotation(
                container_id=str(raw["container_id"]),
                entity_type=PIIType(str(raw["entity_type"])),
                start=int(raw["start"]),
                end=int(raw["end"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Invalid annotation at line {line_number}") from error
        if annotation.container_id not in set(reviewed_ids):
            raise ValueError(f"Annotation line {line_number} is outside reviewed set")
        if annotation.end > len(source_containers[annotation.container_id].text):
            raise ValueError(f"Annotation line {line_number} exceeds source text")
        annotations.append(annotation)
    if len(annotations) != len(set(annotations)):
        raise ValueError("Ground truth contains duplicate annotations")

    return GroundTruthDataset(
        document_sha256=document_sha256,
        extraction_version=extraction_version,
        containers=tuple(reviewed),
        annotations=tuple(annotations),
    )
