from __future__ import annotations

from src.models import JSONValue, PIIEntity, PIIType
import pytest

from src.pseudonymizer import (
    DeterministicPseudonymizer,
    normalize_entity_text,
    replacement_passes_validator,
)


SECRET = b"phase-one-test-key-material"


def person(value: str, **metadata: JSONValue) -> PIIEntity:
    return PIIEntity(
        PIIType.PERSON,
        value,
        0,
        len(value),
        0.9,
        "test_person",
        metadata,
    )


def test_equivalent_values_share_one_cached_replacement() -> None:
    pseudonymizer = DeterministicPseudonymizer(SECRET)
    calls: list[int] = []

    def factory(entity: PIIEntity, seed: int) -> str:
        calls.append(seed)
        return f"Synthetic-{seed % 1000}"

    first = pseudonymizer.replacement_for(person("Alice Smith"), factory)
    second = pseudonymizer.replacement_for(person("  ALICE   SMITH  "), factory)

    assert first == second
    assert len(calls) == 1


def test_linked_entities_can_share_seed_material_across_types() -> None:
    pseudonymizer = DeterministicPseudonymizer(SECRET)
    identity = "internal-person-17"
    person_entity = person(identity, identity_key=identity, link_scope="identity")
    email_text = "person@example.test"
    email_entity = PIIEntity(
        PIIType.EMAIL,
        email_text,
        0,
        len(email_text),
        0.9,
        "test_email",
        {"identity_key": identity, "link_scope": "identity"},
    )

    assert pseudonymizer.stable_seed(person_entity) == pseudonymizer.stable_seed(
        email_entity
    )


@pytest.mark.parametrize(
    ("entity_type", "value", "metadata"),
    [
        (PIIType.PERSON, "Alice Smith", {}),
        (PIIType.EMAIL, "alice.smith@real.test", {}),
        (PIIType.PHONE, "+91 98765 43210", {}),
        (PIIType.COMPANY, "Real Industries Limited", {}),
        (PIIType.ADDRESS, "12 Real Road, Pune 411001, India", {}),
        (PIIType.SSN, "123-45-6789", {}),
        (PIIType.CREDIT_CARD, "4242 4242 4242 4242", {}),
        (PIIType.DOB, "12 May 1988", {}),
        (PIIType.IP_ADDRESS, "203.0.113.17", {"version": 4}),
        (PIIType.IP_ADDRESS, "2001:db8:ffff::7", {"version": 6}),
    ],
)
def test_type_specific_replacements_are_valid_distinct_and_deterministic(
    entity_type: PIIType,
    value: str,
    metadata: dict[str, JSONValue],
) -> None:
    entity = PIIEntity(
        entity_type,
        value,
        0,
        len(value),
        0.95,
        "test",
        metadata,
    )
    first = DeterministicPseudonymizer(SECRET).replacement_for_entity(entity)
    second = DeterministicPseudonymizer(SECRET).replacement_for_entity(entity)

    assert first == second
    assert normalize_entity_text(entity_type, first) != normalize_entity_text(
        entity_type, value
    )
    assert replacement_passes_validator(entity_type, first)


def test_factory_that_reproduces_original_is_rejected() -> None:
    pseudonymizer = DeterministicPseudonymizer(SECRET)
    entity = person("Alice Smith")

    with pytest.raises(ValueError, match="distinct valid replacement"):
        pseudonymizer.replacement_for(entity, lambda item, seed: item.text)
