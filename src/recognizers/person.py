"""Precision-focused PERSON recognition using local NER and context."""

from __future__ import annotations

import re

from src.local_nlp import NERProvider
from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


_PERSON_FORM = re.compile(r"^[A-Z][A-Za-z.'’-]*(?:[ \t]+[A-Z][A-Za-z.'’-]*){1,4}$")
_PERSON_CONTEXT = re.compile(
    r"(?i)\b(?:contact\s+person|chairman|director|chief\s+(?:executive|financial)"
    r"\s+officer|company\s+secretary|compliance\s+officer|engineer)\b"
    r"|\b(?:being|namely)\s*$"
)
_STRONG_PREFIX = re.compile(
    r"(?i)(?:contact\s+person\s*:\s*|\bbeing\s+|\bnamely,?\s+)[^.;:]{0,12}$"
)
_GENERIC_WORDS = frozenset(
    {
        "association",
        "audit",
        "board",
        "branch",
        "committee",
        "company",
        "directors",
        "factors",
        "government",
        "india",
        "international",
        "limited",
        "management",
        "offer",
        "office",
        "parents",
        "registrar",
        "risk",
        "securities",
    }
)


def _trimmed_parts(text: str, start: int, end: int) -> tuple[tuple[int, int], ...]:
    """Split a NER span containing slash-separated contact names."""

    parts: list[tuple[int, int]] = []
    cursor = start
    for raw_part in text[start:end].split("/"):
        left = len(raw_part) - len(raw_part.lstrip())
        right = len(raw_part.rstrip())
        part_start = cursor + left
        part_end = cursor + right
        if part_start < part_end:
            parts.append((part_start, part_end))
        cursor += len(raw_part) + 1
    return tuple(parts)


class PersonRecognizer(Recognizer):
    name = "person_ner_context"
    supported_types = frozenset({PIIType.PERSON})

    def __init__(self, provider: NERProvider, *, minimum_confidence: float = 0.82):
        self._provider = provider
        self._minimum_confidence = minimum_confidence

    @staticmethod
    def _looks_like_person(value: str) -> bool:
        words = {word.casefold().strip(".'’- ") for word in value.split()}
        return bool(_PERSON_FORM.fullmatch(value)) and not words.intersection(
            _GENERIC_WORDS
        )

    def detect(self, text: str) -> list[PIIEntity]:
        entities: list[PIIEntity] = []
        global_person_context = bool(_PERSON_CONTEXT.search(text))
        for ner_span in self._provider.entities(text):
            if ner_span.label not in {"PERSON", "ORG"}:
                continue
            slash_list = "/" in text[ner_span.start : ner_span.end]
            if ner_span.label == "ORG" and not (global_person_context or slash_list):
                continue
            for start, end in _trimmed_parts(text, ner_span.start, ner_span.end):
                value = text[start:end]
                if not self._looks_like_person(value):
                    continue
                prefix = text[max(0, start - 40) : start]
                strong_prefix = bool(_STRONG_PREFIX.search(prefix))
                signals = ["NER_PERSON" if ner_span.label == "PERSON" else "NER_ORG"]
                confidence = 0.82 if ner_span.label == "PERSON" else 0.72
                if slash_list:
                    signals.append("SLASH_SEPARATED_CONTACT_NAMES")
                    confidence += 0.14
                if global_person_context:
                    signals.append("PERSON_ROLE_CONTEXT")
                    confidence += 0.08
                if strong_prefix:
                    signals.append("DIRECT_PERSON_PREFIX")
                    confidence += 0.08
                confidence = min(confidence, 0.98)
                if confidence < self._minimum_confidence:
                    continue
                entities.append(
                    PIIEntity(
                        entity_type=PIIType.PERSON,
                        text=value,
                        start=start,
                        end=end,
                        confidence=confidence,
                        recognizer=self.name,
                        metadata={
                            "strong_context": strong_prefix or slash_list,
                            "signals": tuple(signals),
                            "ner_label": ner_span.label,
                        },
                    )
                )
        return entities
