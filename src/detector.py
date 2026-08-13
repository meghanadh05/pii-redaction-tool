"""Recognizer orchestration without PII-bearing logs."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from src.conflict_resolver import ConflictResolver
from src.models import PIIEntity
from src.recognizers.base import Recognizer


LOGGER = logging.getLogger(__name__)


class DetectionEngine:
    """Run independent recognizers and resolve their overlaps."""

    def __init__(
        self,
        recognizers: Iterable[Recognizer],
        *,
        conflict_resolver: ConflictResolver | None = None,
    ) -> None:
        self._recognizers = tuple(recognizers)
        self._conflict_resolver = conflict_resolver or ConflictResolver()

    def detect(self, text: str) -> list[PIIEntity]:
        candidates: list[PIIEntity] = []
        for recognizer in self._recognizers:
            detections = recognizer.detect(text)
            for entity in detections:
                if (
                    entity.end > len(text)
                    or text[entity.start : entity.end] != entity.text
                ):
                    raise ValueError(
                        f"Recognizer {recognizer.name!r} returned an invalid source span"
                    )
                if entity.entity_type not in recognizer.supported_types:
                    raise ValueError(
                        f"Recognizer {recognizer.name!r} returned an unowned PII type"
                    )
            LOGGER.debug(
                "recognizer=%s candidate_count=%d",
                recognizer.name,
                len(detections),
            )
            candidates.extend(detections)
        resolved = self._conflict_resolver.resolve(candidates)
        LOGGER.info(
            "recognizer_count=%d candidate_count=%d resolved_count=%d",
            len(self._recognizers),
            len(candidates),
            len(resolved),
        )
        return resolved
