"""Shared detection models.

Raw entity text is kept in memory because replacement and evaluation require
it, but it is excluded from repr and from default serialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping, TypeAlias


JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = (
    JSONScalar | list["JSONValue"] | tuple["JSONValue", ...] | Mapping[str, "JSONValue"]
)


def _freeze_json(value: JSONValue) -> JSONValue:
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("metadata keys must be strings")
        return MappingProxyType(
            {key: _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError("metadata values must be JSON-compatible")


def _thaw_json(value: JSONValue) -> JSONValue:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


class PIIType(str, Enum):
    PERSON = "PERSON"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    COMPANY = "COMPANY"
    ADDRESS = "ADDRESS"
    SSN = "SSN"
    CREDIT_CARD = "CREDIT_CARD"
    DOB = "DOB"
    IP_ADDRESS = "IP_ADDRESS"


@dataclass(frozen=True, slots=True)
class PIIEntity:
    """One half-open PII span in a logical text container."""

    entity_type: PIIType
    text: str = field(repr=False)
    start: int
    end: int
    confidence: float
    recognizer: str
    metadata: Mapping[str, JSONValue] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.entity_type, PIIType):
            raise TypeError("entity_type must be a PIIType")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("Entity span must be non-empty with 0 <= start < end")
        if self.end - self.start != len(self.text):
            raise ValueError("Entity text length must equal end - start")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not self.recognizer.strip():
            raise ValueError("recognizer must be non-empty")
        object.__setattr__(self, "metadata", _freeze_json(self.metadata))

    @property
    def span_length(self) -> int:
        return self.end - self.start

    def to_dict(
        self,
        *,
        include_text: bool = False,
        include_metadata: bool = False,
    ) -> dict[str, object]:
        """Return a JSON-compatible mapping, omitting PII-bearing data by default."""

        result: dict[str, object] = {
            "entity_type": self.entity_type.value,
            "start": self.start,
            "end": self.end,
            "confidence": self.confidence,
            "recognizer": self.recognizer,
        }
        if include_text:
            result["text"] = self.text
        if include_metadata:
            result["metadata"] = _thaw_json(self.metadata)
        return result

    def safe_summary(self) -> dict[str, object]:
        """Minimal production-log representation with no entity content."""

        return self.to_dict(include_text=False, include_metadata=False)
