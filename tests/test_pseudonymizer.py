from __future__ import annotations

from src.models import PIIEntity, PIIType
from src.pseudonymizer import DeterministicPseudonymizer


SECRET = b"phase-one-test-key-material"


def person(value: str, **metadata: object) -> PIIEntity:
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
