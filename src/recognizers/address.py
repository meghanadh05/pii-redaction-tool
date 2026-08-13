"""Flexible structural ADDRESS recognition with bounded local NER support."""

from __future__ import annotations

import re

from src.local_nlp import NERProvider
from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


_ADDRESS_PREFIX = re.compile(
    r"(?i)(?:\b(?:registered|corporate|head|branch|mailing|operations?)\s+office"
    r"(?:\s+address)?\s*(?::|at)?\s*|\baddress\s*:\s*|"
    r"\b(?:facility|office)\s+(?:is\s+)?located\s+at\s*|\blocated\s+at\s*)"
)
_INDIAN_POSTAL_CODE = re.compile(
    r"(?<![\w])(?P<pin>[1-9]\d[0-9Il][ \t-]?[0-9Il]\d{2})(?![\w])"
)
_ADDRESS_FEATURE = re.compile(
    r"(?i)\b(?:apartment|avenue|building|bungalow|bunglow|campus|centre|"
    r"chambers?|complex|department|estate|farms?|flat|floor|gymkhana|"
    r"highway|hospital|industrial|lane|level|marg|nagar|office|park|plot|"
    r"road|society|station|street|taluka|tower|unit|village|wing)\b"
)
_PREMISE = re.compile(
    r"(?i)(?:\b(?:flat|floor|plot|room|s\.?\s*no\.?|suite|tower|unit|wing)"
    r"\s*(?:no\.?\s*)?[A-Z0-9]|\b[A-Z]?-?\d{1,4}(?:[/ -]\d{1,4})?\b)"
)
_REGION_FEATURE = re.compile(
    r"(?i)\b(?:India|Maharashtra|Mumbai|Pune|Delhi|Kolkata|Chennai|Bengaluru|"
    r"Hyderabad|Ahmedabad|Nashik|Bhopal|Raigad|Gujarat|Karnataka|Tamil Nadu)\b"
)
_CONTACT_BOUNDARY = re.compile(
    r"(?i)(?:\s*[;|]?\s*\b(?:tel(?:ephone)?|phone|mobile|fax|e-?mail|"
    r"website|contact\s+person)\b\s*:?)"
)
_LEADING_LEGAL_COMPANY = re.compile(
    r"(?i)^.+?\b(?:Private\s+Limited|Public\s+Limited|Limited|Ltd\.?|LLP|"
    r"L\.L\.P\.|Inc\.?|Corporation)\b[\s,;:-]*"
)


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start] in " \t,;:-":
        start += 1
    while end > start and text[end - 1] in " \t,;:.":
        end -= 1
    return start, end


class AddressRecognizer(Recognizer):
    name = "address_structural_local_context"
    supported_types = frozenset({PIIType.ADDRESS})

    def __init__(self, provider: NERProvider, *, minimum_confidence: float = 0.86):
        self._provider = provider
        self._minimum_confidence = minimum_confidence

    def _candidate_bounds(self, text: str) -> tuple[int, int, bool]:
        prefixes = tuple(_ADDRESS_PREFIX.finditer(text))
        explicit_prefix = bool(prefixes)
        start = prefixes[-1].end() if prefixes else len(text) - len(text.lstrip())
        end = len(text.rstrip())
        boundary = _CONTACT_BOUNDARY.search(text, start)
        if boundary:
            end = boundary.start()

        if not explicit_prefix:
            leading = text[start:end]
            legal_company = _LEADING_LEGAL_COMPANY.match(leading)
            if legal_company:
                start += legal_company.end()
            else:
                feature = _ADDRESS_FEATURE.search(text, start, end)
                for span in self._provider.entities(text):
                    if (
                        span.label == "ORG"
                        and span.start <= start + 2
                        and feature is not None
                        and span.end <= feature.start()
                    ):
                        start = span.end
                        break
        start, end = _trim(text, start, end)
        return start, end, explicit_prefix

    def detect(self, text: str) -> list[PIIEntity]:
        start, end, explicit_prefix = self._candidate_bounds(text)
        if start >= end:
            return []
        value = text[start:end]
        postal_matches = tuple(_INDIAN_POSTAL_CODE.finditer(value))
        features = tuple(_ADDRESS_FEATURE.finditer(value))
        premise = bool(_PREMISE.search(value))
        has_region = bool(_REGION_FEATURE.search(value))
        comma_count = value.count(",")

        # A postcode is strong but still requires actual address structure.
        # Without one, require an explicit address label and multiple structural
        # components, or exceptionally dense standalone address structure.
        if postal_matches:
            structural = bool(features) and (premise or has_region or comma_count >= 1)
        else:
            structural = (
                len(features) >= 2
                and premise
                and (explicit_prefix or comma_count >= 1 or len(features) >= 3)
            )
        if not structural:
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
        signals = ["ADDRESS_STRUCTURE"]
        confidence = 0.86
        if postal_matches:
            signals.append("POSTAL_CODE_OR_OCR_VARIANT")
            confidence += 0.05
        if explicit_prefix:
            signals.append("LOCAL_ADDRESS_LABEL")
            confidence += 0.05
        if premise:
            signals.append("PREMISE_COMPONENT")
            confidence += 0.02
        if has_region:
            signals.append("REGION_COMPONENT")
            confidence += 0.01
        if supporting_ner:
            signals.append("NER_LOCATION_SUPPORT")
            confidence += 0.01
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
                    "strong_context": explicit_prefix or bool(postal_matches),
                    "signals": tuple(signals),
                    "supporting_ner_labels": tuple(supporting_ner),
                },
            )
        ]
