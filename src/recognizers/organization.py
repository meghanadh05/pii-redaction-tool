"""COMPANY recognition with precise legal forms and candidate-local context."""

from __future__ import annotations

import re

from src.local_nlp import NERProvider
from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


_LEGAL_SUFFIX = (
    r"Private[ \t]+Limited|Public[ \t]+Limited|Limited|Ltd\.?|LLP|L\.L\.P\.|"
    r"Inc\.?|Incorporated|Corp\.?|Corporation|PLC|P\.L\.C\."
)
_LEGAL_COMPANY = re.compile(
    r"(?<![\w])(?P<company>"
    rf"(?!(?i:{_LEGAL_SUFFIX})\b)[A-Z][A-Za-z0-9&.'’()-]*"
    r"(?:[ \t]+(?:[A-Z][A-Za-z0-9&.'’()-]*|&|and|of|the)){0,10}?"
    rf"[ \t]+(?i:{_LEGAL_SUFFIX}))"
    r"(?![\w])"
)
_ROLE_PREFIX = re.compile(
    r"(?i)^(?:(?:name(?:\s+and\s+logo)?\s+of\s+the\s+)?"
    r"(?:book\s+running\s+lead\s+manager|registrar(?:\s+to\s+the\s+offer)?|"
    r"escrow\s+collection\s+bank|bankers?\s+to\s+the\s+offer|"
    r"monitoring\s+agency|statutory\s+auditors?|share\s+escrow\s+agent)"
    r"\s*[:,-]?\s+)+"
)
_LOCAL_COMPANY_LABEL = re.compile(
    r"(?i)(?:\b(?:company|issuer|corporate\s+promoter|registrar|"
    r"book\s+running\s+lead\s+manager|statutory\s+auditor|auditor|"
    r"industry\s+data\s+provider|share\s+escrow\s+agent|monitoring\s+agency|"
    r"bank|professional\s+firm)\b[^.;:]{0,45}?"
    r"(?:being|namely|is|:|-)\s*)$"
)
_COMMERCIAL_HINT = re.compile(
    r"(?i)\b(?:advisory|analytics|associates|bank|industr(?:y|ies)|infra|"
    r"logistics|motors|ratings|securities|services|technologies|ventures|wealth)\b"
)
_EXCLUDED_ORGANIZATION = re.compile(
    r"(?i)(?:\b(?:act|agreement|bidders?|board|circulars?|committee|"
    r"department|document|government|investors?|managers?|ministry|offer|"
    r"policy|prospectus|regulations?|report|rules?|shareholders?|statements?|"
    r"stock\s+exchanges?|syndicate\s+members?)\b|\bfamily\s+trust\b)"
)
_REGULATORY_BODY = re.compile(
    r"(?i)^(?:SEBI|Reserve Bank of India|Securities and Exchange Board of India|"
    r"Government of India|Ministry\b|Department\b)"
)
_PERSON_LIKE = re.compile(r"^[A-Z][A-Za-z.'’-]*(?:[ \t]+[A-Z][A-Za-z.'’-]*){1,4}$")


def _overlaps(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(
        start < other_end and other_start < end for other_start, other_end in spans
    )


def _trim_legal_boundary(text: str, start: int, end: int) -> tuple[int, int]:
    value = text[start:end]
    formerly = re.match(r"(?i)Formerly[ \t]+", value)
    if formerly:
        start += formerly.end()
        value = text[start:end]
    role_prefix = _ROLE_PREFIX.match(value)
    if role_prefix:
        start += role_prefix.end()
    return start, end


class OrganizationRecognizer(Recognizer):
    name = "company_ner_local_context"
    supported_types = frozenset({PIIType.COMPANY})

    def __init__(self, provider: NERProvider, *, minimum_confidence: float = 0.84):
        self._provider = provider
        self._minimum_confidence = minimum_confidence

    @staticmethod
    def _is_excluded(value: str, *, legal_suffix: bool = False) -> bool:
        if legal_suffix:
            return bool(
                _REGULATORY_BODY.search(value) or re.search(r"(?i)\btrust\b", value)
            )
        return bool(
            _REGULATORY_BODY.search(value)
            or _EXCLUDED_ORGANIZATION.search(value)
            or (
                _PERSON_LIKE.fullmatch(value)
                and not _COMMERCIAL_HINT.search(value)
                and "&" not in value
            )
        )

    def detect(self, text: str) -> list[PIIEntity]:
        entities: list[PIIEntity] = []
        accepted_spans: list[tuple[int, int]] = []
        for match in _LEGAL_COMPANY.finditer(text):
            start, end = _trim_legal_boundary(text, *match.span("company"))
            value = text[start:end]
            if not value or self._is_excluded(value, legal_suffix=True):
                continue
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
                        "signals": ("LEGAL_COMPANY_SUFFIX", "PRECISE_SUFFIX_BOUNDARY"),
                    },
                )
            )
            accepted_spans.append((start, end))

        for ner_span in self._provider.entities(text):
            if ner_span.label != "ORG" or _overlaps(
                ner_span.start, ner_span.end, accepted_spans
            ):
                continue
            raw_value = text[ner_span.start : ner_span.end]
            value = raw_value.strip(" \t,;:.()")
            start = ner_span.start + len(raw_value) - len(raw_value.lstrip(" \t,;:.()"))
            end = start + len(value)
            if not value or self._is_excluded(value):
                continue

            prefix = text[max(0, start - 100) : start]
            local_label = bool(_LOCAL_COMPANY_LABEL.search(prefix))
            commercial_structure = bool(
                _COMMERCIAL_HINT.search(value)
                and ("&" in value or len(value.split()) >= 3)
            )
            whole_container_heading = value == text.strip() and (
                value.isupper() or len(value.split()) <= 5
            )
            if whole_container_heading or not (local_label or commercial_structure):
                continue

            signals = ["NER_ORG"]
            confidence = 0.76
            if local_label:
                signals.append("LOCAL_COMPANY_LABEL")
                confidence += 0.12
            if commercial_structure:
                signals.append("NAMED_COMMERCIAL_STRUCTURE")
                confidence += 0.08
            confidence = min(confidence, 0.94)
            if confidence < self._minimum_confidence:
                continue
            entities.append(
                PIIEntity(
                    entity_type=PIIType.COMPANY,
                    text=value,
                    start=start,
                    end=end,
                    confidence=confidence,
                    recognizer=self.name,
                    metadata={
                        "strong_context": local_label,
                        "signals": tuple(signals),
                    },
                )
            )
        return entities
