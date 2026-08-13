"""Date-of-birth recognition requiring explicit nearby birth context."""

from __future__ import annotations

import re
from datetime import date, datetime

from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


class DOBRecognizer(Recognizer):
    name = "dob_context"
    supported_types = frozenset({PIIType.DOB})
    default_confidence = 0.98

    _month = (
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)"
    )
    _date_pattern = re.compile(
        rf"(?<![\w\d])(?P<date>"
        rf"\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{4}}|"
        rf"\d{{4}}-\d{{1,2}}-\d{{1,2}}|"
        rf"\d{{1,2}}\s+{_month}\s+\d{{4}}|"
        rf"{_month}\s+\d{{1,2}},?\s+\d{{4}}"
        rf")(?![\w\d])",
        re.IGNORECASE,
    )
    _context_before = re.compile(
        r"(?i)(?<!\w)(?P<label>date\s+of\s+birth|birth\s+date|"
        r"d\.?o\.?b\.?|born(?:\s+on)?)(?!\w)\s*(?:is|:|-)?\s*$"
    )
    _context_after = re.compile(
        r"(?i)^\s*(?:\(\s*)?(?P<label>date\s+of\s+birth|birth\s+date|"
        r"d\.?o\.?b\.?)(?!\w)(?:\s*\))?"
    )
    _formats = (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%B %d %Y",
        "%b %d, %Y",
        "%b %d %Y",
    )

    @classmethod
    def normalize(cls, value: str) -> str | None:
        for date_format in cls._formats:
            try:
                parsed = datetime.strptime(value, date_format).date()
            except ValueError:
                continue
            if date(1900, 1, 1) <= parsed <= date.today():
                return parsed.isoformat()
            return None
        return None

    def detect(self, text: str) -> list[PIIEntity]:
        entities: list[PIIEntity] = []
        for match in self._date_pattern.finditer(text):
            value = match.group("date")
            normalized = self.normalize(value)
            if normalized is None:
                continue
            before = text[max(0, match.start() - 48) : match.start()]
            after = text[match.end() : min(len(text), match.end() + 32)]
            preceding_context = self._context_before.search(before)
            following_context = self._context_after.search(after)
            if preceding_context is None and following_context is None:
                continue
            direction = "BEFORE" if preceding_context is not None else "AFTER"
            entities.append(
                PIIEntity(
                    entity_type=PIIType.DOB,
                    text=value,
                    start=match.start("date"),
                    end=match.end("date"),
                    confidence=self.default_confidence,
                    recognizer=self.name,
                    metadata={
                        "normalized": normalized,
                        "validated": True,
                        "strong_context": True,
                        "signals": ("VALID_DATE", f"BIRTH_CONTEXT_{direction}"),
                    },
                )
            )
        return entities
