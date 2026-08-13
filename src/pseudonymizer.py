"""Primitives for deterministic, keyed pseudonym generation."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from src.models import PIIEntity, PIIType


ReplacementFactory = Callable[[PIIEntity, int], str]


def normalize_entity_text(entity_type: PIIType, text: str) -> str:
    """Normalize equivalent appearances before deriving a pseudonym key."""

    text = text.strip()
    if entity_type in {PIIType.PHONE, PIIType.CREDIT_CARD, PIIType.SSN}:
        return re.sub(r"\D", "", text)
    if entity_type in {PIIType.EMAIL, PIIType.IP_ADDRESS}:
        return text.casefold()
    return " ".join(text.casefold().split())


@dataclass(slots=True)
class DeterministicPseudonymizer:
    """Cache replacements by a secret HMAC rather than raw original values.

    Phase 2 factories will use the stable seed to select Faker-backed values or
    format-preserving structured values. An optional ``identity_key`` metadata
    value can link related entities in memory; ``link_scope`` controls which
    related records share seed material.
    """

    secret: bytes = field(repr=False)
    _replacement_cache: dict[str, str] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if len(self.secret) < 16:
            raise ValueError("Pseudonymization secret must contain at least 16 bytes")

    def _digest(self, entity: PIIEntity) -> bytes:
        identity_key = entity.metadata.get("identity_key")
        scope = str(entity.metadata.get("link_scope", entity.entity_type.value))
        if identity_key is None:
            normalized = normalize_entity_text(entity.entity_type, entity.text)
        else:
            # An explicit identity key is type-independent so PERSON and EMAIL
            # records linked to the same identity derive the same seed.
            normalized = " ".join(str(identity_key).casefold().split())
        material = f"{scope}\0{normalized}".encode("utf-8")
        return hmac.new(self.secret, material, hashlib.sha256).digest()

    def stable_seed(self, entity: PIIEntity) -> int:
        return int.from_bytes(self._digest(entity)[:8], byteorder="big", signed=False)

    def replacement_for(
        self,
        entity: PIIEntity,
        factory: ReplacementFactory,
    ) -> str:
        digest = self._digest(entity).hex()
        cache_key = f"{entity.entity_type.value}:{digest}"
        if cache_key not in self._replacement_cache:
            replacement = factory(entity, self.stable_seed(entity))
            if not replacement:
                raise ValueError("Replacement factories must return non-empty text")
            self._replacement_cache[cache_key] = replacement
        return self._replacement_cache[cache_key]
