from __future__ import annotations

from src.identity_linker import EntityReference, IdentityLinker
from src.models import PIIEntity, PIIType
from src.pseudonymizer import DeterministicPseudonymizer


SECRET = b"identity-linking-test-key-material"


def entity(entity_type: PIIType, value: str, start: int = 0) -> PIIEntity:
    return PIIEntity(
        entity_type,
        value,
        start,
        start + len(value),
        0.95,
        "test",
    )


def test_unique_local_person_email_match_produces_coherent_replacements() -> None:
    references = (
        EntityReference(
            "table/r1/c1", "table/r1", entity(PIIType.PERSON, "Anaya Varman")
        ),
        EntityReference(
            "table/r1/c2",
            "table/r1",
            entity(PIIType.EMAIL, "anaya.varman@fictional-company.test"),
        ),
    )

    result = IdentityLinker(SECRET).link(references)
    pseudonymizer = DeterministicPseudonymizer(SECRET)
    fake_person = pseudonymizer.replacement_for_entity(result.references[0].entity)
    fake_email = pseudonymizer.replacement_for_entity(result.references[1].entity)
    tokens = fake_person.casefold().replace(".", "").split()

    assert result.linked_identity_count == 1
    assert result.linked_entity_count == 2
    assert fake_email == f"{tokens[0]}.{tokens[-1]}@example.com"


def test_unmatched_or_ambiguous_email_is_not_forced_into_an_identity() -> None:
    references = (
        EntityReference("c1", "group", entity(PIIType.PERSON, "Anaya Varman")),
        EntityReference("c2", "group", entity(PIIType.PERSON, "Anaya P. Varman")),
        EntityReference(
            "c3", "group", entity(PIIType.EMAIL, "anaya.varman@example.test")
        ),
        EntityReference("c4", "group", entity(PIIType.EMAIL, "support@example.test")),
    )

    result = IdentityLinker(SECRET).link(references)

    assert result.linked_identity_count == 0
    assert result.linked_entity_count == 0
    assert all("identity_key" not in item.entity.metadata for item in result.references)
