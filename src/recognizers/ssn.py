"""Canonical US SSN recognition with basic invalid-range checks."""

from __future__ import annotations

import re

from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


class SSNRecognizer(Recognizer):
    name = "ssn_regex_validated"
    supported_types = frozenset({PIIType.SSN})
    default_confidence = 0.99

    _pattern = re.compile(
        r"(?<!\d)(?P<area>\d{3})-(?P<group>\d{2})-(?P<serial>\d{4})(?!\d)"
    )
    _known_invalid = frozenset({"078-05-1120", "219-09-9999"})

    @staticmethod
    def normalize(value: str) -> str:
        return value

    def detect(self, text: str) -> list[PIIEntity]:
        entities: list[PIIEntity] = []
        for match in self._pattern.finditer(text):
            area = int(match.group("area"))
            group = int(match.group("group"))
            serial = int(match.group("serial"))
            value = match.group(0)
            if (
                area == 0
                or area == 666
                or area >= 900
                or group == 0
                or serial == 0
                or value in self._known_invalid
            ):
                continue
            entities.append(
                PIIEntity(
                    entity_type=PIIType.SSN,
                    text=value,
                    start=match.start(),
                    end=match.end(),
                    confidence=self.default_confidence,
                    recognizer=self.name,
                    metadata={
                        "normalized": self.normalize(value),
                        "validated": True,
                        "signals": ("CANONICAL_SSN", "VALID_RANGES"),
                    },
                )
            )
        return entities
