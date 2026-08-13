"""Postal ADDRESS recognition with NER as supporting, never sole, evidence."""

from __future__ import annotations

import re

from src.local_nlp import NERProvider
from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


_ADDRESS_PREFIX = re.compile(
    r"(?i)(?:\b(?:registered|corporate|head|branch|mailing)\s+office"
    r"(?:\s+address)?\s*:\s*|\baddress\s*:\s*|\blocated\s+at\s*)"
)
_INDIAN_POSTAL_CODE = re.compile(r"(?<!\d)[1-9]\d{2}[ \t]?\d{3}(?!\d)")
_ADDRESS_FEATURE = re.compile(
    r"(?i)\b(?:building|centre|complex|embassy|farms?|floor|industrial|marg|"
    r"nagar|office|park|plot|road|street|taluka|tower|village|wing)\b"
)
_REGION_FEATURE = re.compile(
    r"(?i)\b(?:India|Maharashtra|Mumbai|Pune|Delhi|Kolkata|Chennai|Bengaluru|"
    r"Hyderabad|Ahmedabad)\b"
)


class AddressRecognizer(Recognizer):
    name = "address_postal_ner_context"
    supported_types = frozenset({PIIType.ADDRESS})

    def __init__(self, provider: NERProvider, *, minimum_confidence: float = 0.88):
        self._provider = provider
        self._minimum_confidence = minimum_confidence

    def detect(self, text: str) -> list[PIIEntity]:
        postal_matches = tuple(_INDIAN_POSTAL_CODE.finditer(text))
        if not postal_matches:
            return []

        prefixes = tuple(_ADDRESS_PREFIX.finditer(text))
        start = prefixes[-1].end() if prefixes else len(text) - len(text.lstrip())
        end = len(text.rstrip())
        while end > start and text[end - 1] in ";.":
            end -= 1
        value = text[start:end]
        if not value or not any(
            start <= match.start() < end for match in postal_matches
        ):
            return []

        comma_count = value.count(",")
        has_premise_number = bool(re.search(r"\d", value))
        has_address_feature = bool(_ADDRESS_FEATURE.search(value))
        has_region = bool(_REGION_FEATURE.search(value))
        if comma_count < 2 or not has_premise_number or not has_address_feature:
            return []

        supporting_ner = sorted(
            {
                span.label
                for span in self._provider.entities(text)
                if span.label in {"FAC", "GPE", "LOC"}
                and start < span.end
                and span.start < end
            }
        )
        signals = ["INDIAN_POSTAL_CODE", "ADDRESS_STRUCTURE"]
        confidence = 0.88
        if prefixes:
            signals.append("ADDRESS_LABEL_OR_LOCATED_AT")
            confidence += 0.06
        if has_region:
            signals.append("REGION_COMPONENT")
            confidence += 0.03
        if supporting_ner:
            signals.append("NER_LOCATION_SUPPORT")
            confidence += 0.02
        confidence = min(confidence, 0.99)
        if confidence < self._minimum_confidence:
            return []
        return [
            PIIEntity(
                entity_type=PIIType.ADDRESS,
                text=value,
                start=start,
                end=end,
                confidence=confidence,
                recognizer=self.name,
                metadata={
                    "strong_context": True,
                    "signals": tuple(signals),
                    "supporting_ner_labels": tuple(supporting_ner),
                },
            )
        ]
