"""COMPANY recognition using legal forms, local NER, and exclusions."""

from __future__ import annotations

import re

from src.local_nlp import NERProvider
from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


_LEGAL_COMPANY = re.compile(
    r"(?<![\w])(?P<company>"
    r"[A-Z][A-Za-z0-9&.'’()-]*"
    r"(?:[ \t]+(?:[A-Z][A-Za-z0-9&.'’()-]*|&|and|of|the)){0,10}"
    r"[ \t]+(?i:Private[ \t]+Limited|Public[ \t]+Limited|Limited|Ltd\.?|LLP|L\.L\.P\.))"
    r"(?![\w])"
)
_COMPANY_CONTEXT = re.compile(
    r"(?i)\b(?:company|issuer|corporate\s+promoter|registrar|book\s+running"
    r"\s+lead\s+manager|auditors?|industry\s+data\s+provider)\b"
)
_COMMERCIAL_HINT = re.compile(
    r"(?i)\b(?:advisory|analytics|bank|industr(?:y|ies)|infra|logistics|motors|"
    r"securities|services|wealth)\b"
)
_NON_COMPANY = re.compile(
    r"(?i)^(?:SEBI|India|Company|Registrar|Offer|Government of India|"
    r"Board of Directors|Audit Committee|IPO Committee|Risk Factors|"
    r"Stock Exchanges?)$"
)
_PERSON_ROLE_PREFIX = re.compile(
    r"(?i)(?:\bbeing\s+|\bnamely,?\s+|contact\s+person\s*:\s*)[^.;:]{0,12}$"
)


def _overlaps(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(
        start < other_end and other_start < end for other_start, other_end in spans
    )


class OrganizationRecognizer(Recognizer):
    name = "company_ner_context"
    supported_types = frozenset({PIIType.COMPANY})

    def __init__(self, provider: NERProvider, *, minimum_confidence: float = 0.84):
        self._provider = provider
        self._minimum_confidence = minimum_confidence

    def detect(self, text: str) -> list[PIIEntity]:
        entities: list[PIIEntity] = []
        accepted_spans: list[tuple[int, int]] = []
        for match in _LEGAL_COMPANY.finditer(text):
            start, end = match.span("company")
            value = match.group("company")
            formerly = re.match(r"(?i)Formerly[ \t]+", value)
            if formerly:
                start += formerly.end()
                value = text[start:end]
            entities.append(
                PIIEntity(
                    entity_type=PIIType.COMPANY,
                    text=value,
                    start=start,
                    end=end,
                    confidence=0.97,
                    recognizer=self.name,
                    metadata={
                        "strong_context": True,
                        "signals": ("LEGAL_COMPANY_SUFFIX",),
                    },
                )
            )
            accepted_spans.append((start, end))

        has_company_context = bool(_COMPANY_CONTEXT.search(text))
        for ner_span in self._provider.entities(text):
            if ner_span.label != "ORG" or _overlaps(
                ner_span.start, ner_span.end, accepted_spans
            ):
                continue
            start, end = ner_span.start, ner_span.end
            value = text[start:end].strip(" \t,;:.()")
            start += len(text[start:end]) - len(text[start:end].lstrip(" \t,;:.()"))
            end = start + len(value)
            if not value or _NON_COMPANY.fullmatch(value):
                continue
            if _PERSON_ROLE_PREFIX.search(text[max(0, start - 35) : start]):
                continue
            looks_like_heading = value == text.strip() and (
                value.isupper() or len(value.split()) <= 5
            )
            commercial_hint = bool(_COMMERCIAL_HINT.search(value))
            if (
                looks_like_heading
                or (len(value.split()) < 2 and not commercial_hint)
                or not (has_company_context or commercial_hint)
            ):
                continue
            confidence = 0.76 + (0.08 if has_company_context else 0.0)
            confidence += 0.08 if commercial_hint else 0.0
            if confidence < self._minimum_confidence:
                continue
            entities.append(
                PIIEntity(
                    entity_type=PIIType.COMPANY,
                    text=value,
                    start=start,
                    end=end,
                    confidence=min(confidence, 0.92),
                    recognizer=self.name,
                    metadata={
                        "strong_context": has_company_context,
                        "signals": tuple(
                            signal
                            for signal, present in (
                                ("NER_ORG", True),
                                ("COMPANY_CONTEXT", has_company_context),
                                ("COMMERCIAL_LEXICON", commercial_hint),
                            )
                            if present
                        ),
                    },
                )
            )
        return entities
