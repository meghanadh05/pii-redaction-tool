from __future__ import annotations

import json

import pytest

from src.models import PIIEntity, PIIType


def test_entity_is_privacy_safe_by_default() -> None:
    raw_value = "person@example.test"
    entity = PIIEntity(
        entity_type=PIIType.EMAIL,
        text=raw_value,
        start=4,
        end=4 + len(raw_value),
        confidence=0.99,
        recognizer="test_email",
        metadata={"signals": ["REGEX", "DOMAIN_SHAPE"]},
    )

    assert raw_value not in repr(entity)
    assert raw_value not in json.dumps(entity.to_dict())
    assert entity.to_dict(include_text=True)["text"] == raw_value
    with pytest.raises(TypeError):
        entity.metadata["new"] = "value"  # type: ignore[index]
    with pytest.raises(AttributeError):
        entity.metadata["signals"].append("MUTATION")  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("start", "end", "text", "confidence"),
    [(-1, 1, "ab", 0.5), (1, 1, "", 0.5), (0, 1, "ab", 0.5), (0, 1, "a", 1.1)],
)
def test_entity_rejects_invalid_spans_and_confidence(
    start: int,
    end: int,
    text: str,
    confidence: float,
) -> None:
    with pytest.raises(ValueError):
        PIIEntity(PIIType.PERSON, text, start, end, confidence, "test")
