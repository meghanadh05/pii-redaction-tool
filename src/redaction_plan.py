"""Preflighted, privacy-safe replacement planning for DOCX containers."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from src.detector import DetectionEngine
from src.docx_processor import StoryKind, TextContainer, TextReplacement
from src.identity_linker import EntityReference, IdentityLinker
from src.models import PIIEntity, PIIType
from src.pseudonymizer import DeterministicPseudonymizer, normalize_entity_text


_TABLE_ROW = re.compile(r"^(?P<row>.+/r\d{4})/c\d{4}/")


def context_key_for_container(container_id: str) -> str:
    """Return a conservative local context used only for identity linking."""

    match = _TABLE_ROW.match(container_id)
    return match.group("row") if match else container_id


@dataclass(frozen=True, slots=True)
class PlannedReplacement:
    container_id: str
    story_type: StoryKind
    entity: PIIEntity = field(repr=False)
    replacement: str = field(repr=False)
    affected_run_count: int
    mirror_count: int


@dataclass(frozen=True, slots=True)
class ReplacementConflict:
    container_id: str
    reason: str
    entity_types: tuple[PIIType, ...]
    spans: tuple[tuple[int, int], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "container_id": self.container_id,
            "reason": self.reason,
            "entity_types": [item.value for item in self.entity_types],
            "spans": [list(span) for span in self.spans],
        }


@dataclass(frozen=True, slots=True)
class RedactionPlan:
    replacements: tuple[PlannedReplacement, ...]
    conflicts: tuple[ReplacementConflict, ...]
    linked_identity_count: int
    linked_entity_count: int
    container_counts: Mapping[StoryKind, int]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "container_counts", MappingProxyType(dict(self.container_counts))
        )

    def summary(self) -> dict[str, object]:
        by_type = Counter(item.entity.entity_type.value for item in self.replacements)
        conflict_reasons = Counter(item.reason for item in self.conflicts)
        return {
            "privacy_safe": True,
            "dry_run": True,
            "document_mutated": False,
            "document_write_enabled": False,
            "container_count": sum(self.container_counts.values()),
            "containers_by_story": {
                story.value: self.container_counts.get(story, 0) for story in StoryKind
            },
            "planned_replacement_count": len(self.replacements),
            "planned_replacements_by_type": {
                entity_type.value: by_type.get(entity_type.value, 0)
                for entity_type in PIIType
            },
            "cross_run_replacement_count": sum(
                item.affected_run_count > 1 for item in self.replacements
            ),
            "text_box_replacement_count": sum(
                item.story_type is StoryKind.TEXT_BOX_PARAGRAPH
                for item in self.replacements
            ),
            "mirrored_representation_update_count": sum(
                item.mirror_count for item in self.replacements
            ),
            "linked_identity_count": self.linked_identity_count,
            "linked_entity_count": self.linked_entity_count,
            "conflict_count": len(self.conflicts),
            "conflicts_by_reason": dict(sorted(conflict_reasons.items())),
            "quality_gate": "BLOCKED_BY_UNTOUCHED_HOLDOUT",
        }


class ReplacementPlanner:
    def __init__(
        self,
        detector: DetectionEngine,
        pseudonymizer: DeterministicPseudonymizer,
        *,
        identity_linker: IdentityLinker | None = None,
    ) -> None:
        self._detector = detector
        self._pseudonymizer = pseudonymizer
        self._identity_linker = identity_linker

    def build(self, containers: tuple[TextContainer, ...]) -> RedactionPlan:
        references = tuple(
            EntityReference(
                container_id=container.id,
                context_key=context_key_for_container(container.id),
                entity=entity,
            )
            for container in containers
            for entity in self._detector.detect(container.text)
        )
        if self._identity_linker is None:
            linked_references = references
            linked_identity_count = 0
            linked_entity_count = 0
        else:
            link_result = self._identity_linker.link(references)
            linked_references = link_result.references
            linked_identity_count = link_result.linked_identity_count
            linked_entity_count = link_result.linked_entity_count

        by_container = {container.id: container for container in containers}
        grouped: dict[str, list[EntityReference]] = {}
        for reference in linked_references:
            grouped.setdefault(reference.container_id, []).append(reference)

        conflicts: list[ReplacementConflict] = []
        planned: list[PlannedReplacement] = []
        consistency: dict[tuple[PIIType, str], str] = {}
        for container_id, items in grouped.items():
            container = by_container[container_id]
            ordered = sorted(
                items, key=lambda item: (item.entity.start, item.entity.end)
            )
            container_has_conflict = False
            for previous, current in zip(ordered, ordered[1:]):
                if current.entity.start < previous.entity.end:
                    container_has_conflict = True
                    conflicts.append(
                        ReplacementConflict(
                            container_id=container_id,
                            reason="OVERLAPPING_DETECTIONS",
                            entity_types=(
                                previous.entity.entity_type,
                                current.entity.entity_type,
                            ),
                            spans=(
                                (previous.entity.start, previous.entity.end),
                                (current.entity.start, current.entity.end),
                            ),
                        )
                    )
            if container_has_conflict:
                continue

            text_replacements: list[TextReplacement] = []
            container_planned: list[PlannedReplacement] = []
            for reference in ordered:
                entity = reference.entity
                replacement = self._pseudonymizer.replacement_for_entity(entity)
                identity = (
                    entity.entity_type,
                    normalize_entity_text(entity.entity_type, entity.text),
                )
                previous_replacement = consistency.setdefault(identity, replacement)
                if previous_replacement != replacement:
                    container_has_conflict = True
                    conflicts.append(
                        ReplacementConflict(
                            container_id=container_id,
                            reason="INCONSISTENT_REPEATED_ENTITY",
                            entity_types=(entity.entity_type,),
                            spans=((entity.start, entity.end),),
                        )
                    )
                    continue
                text_replacements.append(
                    TextReplacement(entity.start, entity.end, replacement)
                )
                container_planned.append(
                    PlannedReplacement(
                        container_id=container_id,
                        story_type=container.story_type,
                        entity=entity,
                        replacement=replacement,
                        affected_run_count=len(
                            container.logical.map_span(entity.start, entity.end)
                        ),
                        mirror_count=len(container.mirrors),
                    )
                )
            if text_replacements and not container_has_conflict:
                try:
                    container.validate_rewrite(text_replacements)
                except ValueError:
                    conflicts.append(
                        ReplacementConflict(
                            container_id=container_id,
                            reason="UNSAFE_DOCX_REWRITE",
                            entity_types=tuple(
                                item.entity.entity_type for item in ordered
                            ),
                            spans=tuple(
                                (item.entity.start, item.entity.end) for item in ordered
                            ),
                        )
                    )
                else:
                    planned.extend(container_planned)

        return RedactionPlan(
            replacements=tuple(planned),
            conflicts=tuple(conflicts),
            linked_identity_count=linked_identity_count,
            linked_entity_count=linked_entity_count,
            container_counts=dict(Counter(item.story_type for item in containers)),
        )


def apply_redaction_plan(
    containers: tuple[TextContainer, ...], plan: RedactionPlan
) -> None:
    """Apply only a conflict-free plan after preflighting every container."""

    if plan.conflicts:
        raise ValueError("Cannot apply a replacement plan containing conflicts")
    by_container = {container.id: container for container in containers}
    grouped: dict[str, list[TextReplacement]] = {}
    for item in plan.replacements:
        container = by_container[item.container_id]
        if container.text[item.entity.start : item.entity.end] != item.entity.text:
            raise ValueError("Replacement plan no longer matches source container text")
        grouped.setdefault(item.container_id, []).append(
            TextReplacement(item.entity.start, item.entity.end, item.replacement)
        )
    for container_id, replacements in grouped.items():
        by_container[container_id].validate_rewrite(replacements)
    for container_id, replacements in grouped.items():
        by_container[container_id].rewrite(replacements)
