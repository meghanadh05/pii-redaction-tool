"""Local spaCy access with a small privacy-conscious result cache."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import metadata
from typing import Protocol

import spacy
from spacy.language import Language


DEFAULT_MODEL = "en_core_web_sm"


@dataclass(frozen=True, slots=True)
class NERSpan:
    label: str
    start: int
    end: int


class NERProvider(Protocol):
    def entities(self, text: str) -> tuple[NERSpan, ...]: ...


class LocalSpacyProvider:
    """Run a packaged spaCy pipeline without network calls.

    The short LRU exists only to share one parse between semantic recognizers
    called consecutively for a container. It is bounded so document text is not
    retained indefinitely by the detector.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._pipeline: Language | None = None

    def _load(self) -> Language:
        if self._pipeline is None:
            self._pipeline = spacy.load(self.model_name)
        return self._pipeline

    @lru_cache(maxsize=8)
    def entities(self, text: str) -> tuple[NERSpan, ...]:
        document = self._load()(text)
        return tuple(
            NERSpan(entity.label_, entity.start_char, entity.end_char)
            for entity in document.ents
        )

    def model_versions(self) -> dict[str, str]:
        return {
            "spacy": spacy.__version__,
            "model_name": self.model_name,
            "model_version": metadata.version(self.model_name.replace("_", "-")),
        }
