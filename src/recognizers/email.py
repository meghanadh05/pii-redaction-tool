"""Practical email recognition without attempting all of RFC 5322."""

from __future__ import annotations

import re

from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


class EmailRecognizer(Recognizer):
    name = "email_regex"
    supported_types = frozenset({PIIType.EMAIL})
    default_confidence = 0.99

    _pattern = re.compile(
        r"(?<![\w.!#$%&'*+/=?^_`{|}~-])"
        r"(?P<email>"
        r"[A-Z0-9!#$%&'*+/=?^_`{|}~-]+"
        r"(?:\.[A-Z0-9!#$%&'*+/=?^_`{|}~-]+)*"
        r"@"
        r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
        r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+"
        r")"
        r"(?![\w@-])",
        re.IGNORECASE,
    )

    @staticmethod
    def normalize(value: str) -> str:
        # SMTP local-parts can technically be case-sensitive. Case-folding is
        # the practical identity rule for deterministic redaction.
        return value.casefold()

    @staticmethod
    def _is_inside_url(text: str, start: int, end: int) -> bool:
        token_start = max(
            text.rfind(" ", max(0, start - 120), start),
            text.rfind("\t", max(0, start - 120), start),
            text.rfind("\n", max(0, start - 120), start),
        )
        token = text[token_start + 1 : end]
        at_position = token.rfind("@")
        return 0 <= token.find("://") < at_position

    def detect(self, text: str) -> list[PIIEntity]:
        entities: list[PIIEntity] = []
        for match in self._pattern.finditer(text):
            start, end = match.span("email")
            value = match.group("email")
            if len(value) > 254 or self._is_inside_url(text, start, end):
                continue
            local, domain = value.rsplit("@", maxsplit=1)
            if len(local) > 64 or any(len(label) > 63 for label in domain.split(".")):
                continue
            entities.append(
                PIIEntity(
                    entity_type=PIIType.EMAIL,
                    text=value,
                    start=start,
                    end=end,
                    confidence=self.default_confidence,
                    recognizer=self.name,
                    metadata={
                        "normalized": self.normalize(value),
                        "validated": True,
                        "signals": ("EMAIL_PATTERN", "DOMAIN_LABELS"),
                    },
                )
            )
        return entities
