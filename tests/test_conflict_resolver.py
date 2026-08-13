from __future__ import annotations

from src.conflict_resolver import ConflictResolver
from src.models import JSONValue, PIIEntity, PIIType


def entity(
    entity_type: PIIType,
    text: str,
    start: int,
    confidence: float,
    recognizer: str,
    **metadata: JSONValue,
) -> PIIEntity:
    return PIIEntity(
        entity_type,
        text,
        start,
        start + len(text),
        confidence,
        recognizer,
        metadata,
    )


def test_validated_structured_detection_beats_overlapping_weak_ner() -> None:
    weak_person = entity(PIIType.PERSON, "name@example", 0, 0.99, "generic_ner")
    validated_email = entity(
        PIIType.EMAIL,
        "name@example.test",
        0,
        0.91,
        "email_regex",
        validated=True,
    )

    assert ConflictResolver().resolve([weak_person, validated_email]) == [
        validated_email
    ]


def test_longer_span_wins_equal_evidence_and_confidence() -> None:
    short = entity(PIIType.ADDRESS, "Main Road", 4, 0.90, "address_rules")
    long = entity(
        PIIType.ADDRESS,
        "12 Main Road",
        1,
        0.90,
        "address_rules",
    )

    assert ConflictResolver().resolve([short, long]) == [long]


def test_non_overlapping_results_are_returned_in_source_order() -> None:
    later = entity(PIIType.EMAIL, "a@b.test", 20, 0.9, "email", validated=True)
    earlier = entity(PIIType.PERSON, "A Name", 2, 0.9, "person")

    assert ConflictResolver().resolve([later, earlier]) == [earlier, later]
