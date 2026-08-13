"""Deterministic resolution of overlapping detections."""

from __future__ import annotations

from collections.abc import Iterable

from src.models import PIIEntity, PIIType


_STRUCTURED_TYPES = frozenset(
    {
        PIIType.EMAIL,
        PIIType.PHONE,
        PIIType.SSN,
        PIIType.CREDIT_CARD,
        PIIType.IP_ADDRESS,
    }
)

_TYPE_PRIORITY = {
    PIIType.CREDIT_CARD: 90,
    PIIType.SSN: 90,
    PIIType.EMAIL: 80,
    PIIType.IP_ADDRESS: 80,
    PIIType.PHONE: 70,
    PIIType.DOB: 60,
    PIIType.ADDRESS: 50,
    PIIType.PERSON: 40,
    PIIType.COMPANY: 30,
}


def spans_overlap(left: PIIEntity, right: PIIEntity) -> bool:
    return left.start < right.end and right.start < left.end


class ConflictResolver:
    """Select a non-overlapping set using evidence, confidence, and length.

    A structured detection receives the highest evidence tier only when its
    recognizer explicitly records ``metadata["validated"] is True``. Strong
    contextual detections receive the next tier. This prevents a weak regex
    shape from outranking better contextual evidence merely because its type is
    structured.
    """

    @staticmethod
    def _evidence_tier(entity: PIIEntity) -> int:
        if (
            entity.entity_type in _STRUCTURED_TYPES
            and entity.metadata.get("validated") is True
        ):
            return 3
        if entity.metadata.get("strong_context") is True:
            return 2
        return 1

    def _rank(self, entity: PIIEntity) -> tuple[object, ...]:
        return (
            -self._evidence_tier(entity),
            -entity.confidence,
            -entity.span_length,
            -_TYPE_PRIORITY[entity.entity_type],
            entity.start,
            entity.end,
            entity.recognizer,
            entity.entity_type.value,
        )

    def resolve(self, entities: Iterable[PIIEntity]) -> list[PIIEntity]:
        """Return deterministic, start-sorted, non-overlapping detections."""

        selected: list[PIIEntity] = []
        for candidate in sorted(entities, key=self._rank):
            if any(spans_overlap(candidate, existing) for existing in selected):
                continue
            selected.append(candidate)
        return sorted(
            selected,
            key=lambda entity: (
                entity.start,
                entity.end,
                entity.entity_type.value,
                entity.recognizer,
            ),
        )
