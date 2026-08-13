"""PERSON recognition using local roles, list parsing, and guarded NER."""

from __future__ import annotations

import re

from src.local_nlp import NERProvider
from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


_PERSON_FORM = re.compile(r"^[A-Z][A-Za-z.'’-]*(?:[ \t]+[A-Z][A-Za-z.'’-]*){1,4}$")
_ROLE_INTRO = re.compile(
    r"(?i)\b(?:contact\s+persons?|promoters?|directors?|chairman|"
    r"chief\s+(?:executive|financial)\s+officer|CEO|CFO|"
    r"company\s+secretary(?:\s+and\s+compliance\s+officer)?|"
    r"compliance\s+officer|managing\s+director|whole-time\s+director|"
    r"joint\s+managing\s+director|engineer)\b"
    r"(?:\s+of\s+our\s+company)?(?:\s*,?\s*(?:are|being|namely))?\s*[:,]?\s*"
)
_DIRECT_ROLE_PREFIX = re.compile(
    r"(?i)(?:contact\s+persons?\s*:\s*|\b(?:being|namely),?\s+|"
    r"\b(?:CEO|CFO)\s*:\s*)[^.;:]{0,28}$"
)
_ROLE_TITLE_PATTERN = (
    r"(?:chairman|chairperson|(?:non[- ]executive|executive|independent|"
    r"whole[- ]time|managing|joint\s+managing)?\s*director|"
    r"chief\s+(?:executive|financial|operating|risk)\s+officer|"
    r"company\s+secretary|compliance\s+officer|CEO|CFO)"
)
_TRAILING_ROLE_ANNOTATION = re.compile(
    rf"(?i)(?:\s*\(\s*{_ROLE_TITLE_PATTERN}\s*\)|"
    rf"\s*[-–—]\s*{_ROLE_TITLE_PATTERN})\s*$"
)
_REGION_STOP = re.compile(
    r"(?i)(?:[.]|,\s*(?:company\s+secretary|compliance\s+officer|director|"
    r"chairman|CEO|CFO)\b|\b(?:telephone|phone|mobile|e-?mail|website|for\s+further|"
    r"are\s+the\s+promoters?|is\s+the\s+promoter|responsible\s+for|"
    r"who|whose|which|shall|will|having)\b)"
)
_LIST_SEPARATOR = re.compile(r"\s*(?:/|,|;|\band\b)\s*", re.IGNORECASE)
_GENERIC_WORDS = frozenset(
    {
        "address",
        "advisory",
        "apartment",
        "applicable",
        "association",
        "associates",
        "audit",
        "authority",
        "avenue",
        "bank",
        "board",
        "branch",
        "building",
        "business",
        "campus",
        "capital",
        "centre",
        "chairman",
        "chairperson",
        "chief",
        "city",
        "clause",
        "committee",
        "company",
        "complex",
        "compliance",
        "controls",
        "corporate",
        "council",
        "department",
        "director",
        "directors",
        "estate",
        "exchange",
        "executive",
        "factors",
        "financial",
        "flat",
        "floor",
        "foundation",
        "framework",
        "government",
        "governance",
        "hospital",
        "house",
        "india",
        "industrial",
        "industries",
        "institute",
        "internal",
        "international",
        "law",
        "lane",
        "limited",
        "management",
        "managing",
        "nagar",
        "office",
        "officer",
        "management",
        "offer",
        "operating",
        "parents",
        "park",
        "partners",
        "plaza",
        "plot",
        "policy",
        "promoter",
        "promoters",
        "provisions",
        "pursuant",
        "registrar",
        "regulation",
        "report",
        "responsibilities",
        "risk",
        "road",
        "secretary",
        "section",
        "securities",
        "services",
        "shareholder",
        "station",
        "street",
        "subject",
        "terms",
        "tower",
        "trust",
        "university",
    }
)


def _clean_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start] in " \t,;:/([":
        start += 1
    while end > start and text[end - 1] in " \t,;:/*":
        end -= 1
    role_annotation = _TRAILING_ROLE_ANNOTATION.search(text, start, end)
    if role_annotation:
        end = role_annotation.start()
    while end > start and text[end - 1] in " \t,;:/*)]":
        end -= 1
    honorific = re.match(r"(?i)(?:Mr|Mrs|Ms|Dr)\.?\s+", text[start:end])
    if honorific:
        start += honorific.end()
    return start, end


def _split_parts(text: str, start: int, end: int) -> tuple[tuple[int, int], ...]:
    parts: list[tuple[int, int]] = []
    cursor = start
    for match in _LIST_SEPARATOR.finditer(text, start, end):
        part_start, part_end = _clean_span(text, cursor, match.start())
        if part_start < part_end:
            parts.append((part_start, part_end))
        cursor = match.end()
    part_start, part_end = _clean_span(text, cursor, end)
    if part_start < part_end:
        parts.append((part_start, part_end))
    return tuple(parts)


class PersonRecognizer(Recognizer):
    name = "person_ner_local_context"
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

    @staticmethod
    def _role_regions(text: str) -> tuple[tuple[int, int], ...]:
        regions: list[tuple[int, int]] = []
        for match in _ROLE_INTRO.finditer(text):
            start = match.end()
            remainder = text[start : min(len(text), start + 300)]
            stop = _REGION_STOP.search(remainder)
            end = start + (stop.start() if stop else len(remainder))
            if start < end:
                regions.append((start, end))
        return tuple(regions)

    def _entity(
        self,
        text: str,
        start: int,
        end: int,
        *,
        confidence: float,
        signals: tuple[str, ...],
        ner_label: str | None = None,
    ) -> PIIEntity | None:
        start, end = _clean_span(text, start, end)
        value = text[start:end]
        if not self._looks_like_person(value) or confidence < self._minimum_confidence:
            return None
        metadata: dict[str, object] = {
            "strong_context": "LOCAL_PERSON_ROLE" in signals
            or "PERSON_LIST_CONTEXT" in signals,
            "signals": signals,
        }
        if ner_label is not None:
            metadata["ner_label"] = ner_label
        return PIIEntity(
            entity_type=PIIType.PERSON,
            text=value,
            start=start,
            end=end,
            confidence=min(confidence, 0.98),
            recognizer=self.name,
            metadata=metadata,  # type: ignore[arg-type]
        )

    def detect(self, text: str) -> list[PIIEntity]:
        entities: dict[tuple[int, int], PIIEntity] = {}
        role_regions = self._role_regions(text)
        for start, end in role_regions:
            for part_start, part_end in _split_parts(text, start, end):
                entity = self._entity(
                    text,
                    part_start,
                    part_end,
                    confidence=0.96,
                    signals=("PERSON_LIST_CONTEXT", "LOCAL_PERSON_ROLE"),
                )
                if entity is not None:
                    entities[(entity.start, entity.end)] = entity

        for ner_span in self._provider.entities(text):
            if ner_span.label not in {"PERSON", "ORG"}:
                continue
            split_spans = _split_parts(text, ner_span.start, ner_span.end)
            list_like = len(split_spans) > 1
            person_shaped_list = list_like and all(
                self._looks_like_person(text[start:end]) for start, end in split_spans
            )
            locally_qualified = any(
                region_start <= ner_span.start < region_end
                for region_start, region_end in role_regions
            ) or bool(
                _DIRECT_ROLE_PREFIX.search(
                    text[max(0, ner_span.start - 70) : ner_span.start]
                )
            )
            if ner_span.label == "ORG" and not (
                locally_qualified or person_shaped_list
            ):
                continue
            for start, end in split_spans:
                signals = ["NER_PERSON" if ner_span.label == "PERSON" else "NER_ORG"]
                confidence = 0.84 if ner_span.label == "PERSON" else 0.72
                if list_like:
                    signals.append("SEPARATED_PERSON_LIST")
                    confidence += 0.12
                if locally_qualified:
                    signals.append("LOCAL_PERSON_ROLE")
                    confidence += 0.14
                entity = self._entity(
                    text,
                    start,
                    end,
                    confidence=confidence,
                    signals=tuple(signals),
                    ner_label=ner_span.label,
                )
                if entity is not None:
                    entities[(entity.start, entity.end)] = entity
        return sorted(entities.values(), key=lambda item: (item.start, item.end))
