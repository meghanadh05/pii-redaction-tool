"""Conservative PERSON-to-EMAIL identity linking, separate from detection."""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass

from src.models import PIIEntity, PIIType


@dataclass(frozen=True, slots=True)
class EntityReference:
    container_id: str
    context_key: str
    entity: PIIEntity


@dataclass(frozen=True, slots=True)
class IdentityLinkResult:
    references: tuple[EntityReference, ...]
    linked_identity_count: int
    linked_entity_count: int


def _person_tokens(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z]+", value.casefold()))


def _email_local(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.split("@", maxsplit=1)[0].casefold())


def _email_matches_person(email: str, person: str) -> bool:
    tokens = _person_tokens(person)
    if len(tokens) < 2:
        return False
    local = _email_local(email)
    first, last = tokens[0], tokens[-1]
    return (first in local and last in local) or local.startswith(first[0] + last)


class IdentityLinker:
    """Link only unique name/email matches inside an explicit local context."""

    def __init__(self, secret: bytes) -> None:
        if len(secret) < 16:
            raise ValueError("Identity-link secret must contain at least 16 bytes")
        self._secret = secret

    def _identity_key(self, context_key: str, person: PIIEntity) -> str:
        material = f"{context_key}\0{' '.join(_person_tokens(person.text))}".encode()
        digest = hmac.new(self._secret, material, hashlib.sha256).hexdigest()
        return f"identity-{digest}"

    @staticmethod
    def _with_link(entity: PIIEntity, identity_key: str) -> PIIEntity:
        metadata = dict(entity.metadata)
        metadata.update(
            {
                "identity_key": identity_key,
                "link_scope": "identity",
                "identity_link_signal": "LOCAL_EMAIL_NAME_MATCH",
            }
        )
        return PIIEntity(
            entity_type=entity.entity_type,
            text=entity.text,
            start=entity.start,
            end=entity.end,
            confidence=entity.confidence,
            recognizer=entity.recognizer,
            metadata=metadata,
        )

    def link(self, references: tuple[EntityReference, ...]) -> IdentityLinkResult:
        groups: dict[str, list[tuple[int, EntityReference]]] = {}
        for index, reference in enumerate(references):
            groups.setdefault(reference.context_key, []).append((index, reference))

        replacements: dict[int, EntityReference] = {}
        linked_identities = 0
        for context_key, items in groups.items():
            people = [
                item for item in items if item[1].entity.entity_type is PIIType.PERSON
            ]
            emails = [
                item for item in items if item[1].entity.entity_type is PIIType.EMAIL
            ]
            candidate_pairs = [
                (person, email)
                for person in people
                for email in emails
                if _email_matches_person(email[1].entity.text, person[1].entity.text)
            ]
            person_counts = {
                person[0]: sum(pair[0][0] == person[0] for pair in candidate_pairs)
                for person in people
            }
            email_counts = {
                email[0]: sum(pair[1][0] == email[0] for pair in candidate_pairs)
                for email in emails
            }
            for person, email in candidate_pairs:
                if person_counts[person[0]] != 1 or email_counts[email[0]] != 1:
                    continue
                identity_key = self._identity_key(context_key, person[1].entity)
                for index, reference in (person, email):
                    replacements[index] = EntityReference(
                        container_id=reference.container_id,
                        context_key=reference.context_key,
                        entity=self._with_link(reference.entity, identity_key),
                    )
                linked_identities += 1

        linked = tuple(
            replacements.get(index, reference)
            for index, reference in enumerate(references)
        )
        return IdentityLinkResult(
            references=linked,
            linked_identity_count=linked_identities,
            linked_entity_count=len(replacements),
        )
