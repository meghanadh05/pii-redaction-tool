"""Conservative India-aware and international phone recognition."""

from __future__ import annotations

import re

from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


class PhoneRecognizer(Recognizer):
    name = "phone_regex_context"
    supported_types = frozenset({PIIType.PHONE})

    _candidate = re.compile(
        r"(?<![\w.])(?P<phone>(?:\+\s*)?(?:\(\d{2,4}\)|\d)"
        r"(?:[\s().-]*\d){7,14})(?![\w.])"
    )
    _positive_context = re.compile(
        r"(?i)\b(?:tel(?:ephone)?|phone|mobile|mob\.?|contact(?:\s+number)?|"
        r"facsimile|fax)\b[^\n]{0,28}$"
    )
    _negative_context = re.compile(
        r"(?i)\b(?:CIN|DIN|ISIN|SEBI|registration|reference|folio|application|"
        r"invoice|order|ticket|offer|shares?|amount|million|crore|lakh|page|"
        r"financial\s+year)\b[^\n]{0,36}$"
    )
    _currency_nearby = re.compile(r"(?:₹|\$|€|£)\s*[\d,.\s]*$")

    @staticmethod
    def normalize(value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if value.lstrip().startswith("+"):
            return f"+{digits}"
        if len(digits) == 10 and digits[0] in "6789":
            return f"+91{digits}"
        return digits

    @staticmethod
    def _separator_count(value: str) -> int:
        return sum(character in " -()." for character in value)

    def _classify(
        self,
        value: str,
        *,
        has_positive_context: bool,
    ) -> tuple[float, tuple[str, ...]] | None:
        digits = re.sub(r"\D", "", value)
        explicit_plus = value.lstrip().startswith("+")
        separator_count = self._separator_count(value)
        if not 8 <= len(digits) <= 15:
            return None

        if explicit_plus:
            # A plus sign is strong international-dialing evidence, but require
            # a plausible country-code/number length and more than one repeated
            # digit to avoid formatted identifiers.
            if len(digits) < 9 or len(set(digits)) < 3:
                return None
            return 0.98, ("EXPLICIT_COUNTRY_CODE", "PHONE_LENGTH")

        if len(digits) == 10 and digits[0] in "6789":
            return 0.94, ("INDIAN_MOBILE_PREFIX", "PHONE_LENGTH")

        if digits.startswith("0") and len(digits) in {10, 11} and separator_count >= 2:
            return 0.95, ("INDIAN_TRUNK_PREFIX", "GROUPED_LANDLINE")

        if has_positive_context and separator_count >= 1:
            return 0.93, ("PHONE_LABEL", "GROUPED_NUMBER", "PHONE_LENGTH")

        return None

    def detect(self, text: str) -> list[PIIEntity]:
        entities: list[PIIEntity] = []
        for match in self._candidate.finditer(text):
            value = match.group("phone")
            context = text[max(0, match.start() - 60) : match.start()]
            positive = self._positive_context.search(context) is not None
            if self._negative_context.search(context) or self._currency_nearby.search(
                context
            ):
                continue
            classification = self._classify(value, has_positive_context=positive)
            if classification is None:
                continue
            confidence, signals = classification
            entities.append(
                PIIEntity(
                    entity_type=PIIType.PHONE,
                    text=value,
                    start=match.start("phone"),
                    end=match.end("phone"),
                    confidence=confidence,
                    recognizer=self.name,
                    metadata={
                        "normalized": self.normalize(value),
                        "validated": True,
                        "signals": signals,
                    },
                )
            )
        return entities
