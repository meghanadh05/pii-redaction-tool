"""Extensible recognizer contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from src.models import PIIEntity, PIIType


class Recognizer(ABC):
    """Detect one or more owned PII categories in a logical text string."""

    name: ClassVar[str]
    supported_types: ClassVar[frozenset[PIIType]]

    @abstractmethod
    def detect(self, text: str) -> list[PIIEntity]:
        """Return detections whose offsets refer to ``text``."""
