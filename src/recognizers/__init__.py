"""PII recognizers and explicit structured/semantic detector sets."""

from src.local_nlp import LocalSpacyProvider

from .address import AddressRecognizer
from .base import Recognizer
from .credit_card import CreditCardRecognizer
from .dob import DOBRecognizer
from .email import EmailRecognizer
from .ip_address import IPAddressRecognizer
from .organization import OrganizationRecognizer
from .person import PersonRecognizer
from .phone import PhoneRecognizer
from .ssn import SSNRecognizer


def structured_recognizers() -> tuple[Recognizer, ...]:
    """Return the deterministic Phase 2A recognizers in explicit order."""

    return (
        EmailRecognizer(),
        PhoneRecognizer(),
        SSNRecognizer(),
        CreditCardRecognizer(),
        IPAddressRecognizer(),
        DOBRecognizer(),
    )


def semantic_recognizers() -> tuple[Recognizer, ...]:
    """Return semantic recognizers sharing one local spaCy parse provider."""

    provider = LocalSpacyProvider()
    return (
        PersonRecognizer(provider),
        OrganizationRecognizer(provider),
        AddressRecognizer(provider),
    )


def all_recognizers() -> tuple[Recognizer, ...]:
    """Return the complete Phase 2B detector set."""

    return (*structured_recognizers(), *semantic_recognizers())


__all__ = [
    "AddressRecognizer",
    "CreditCardRecognizer",
    "DOBRecognizer",
    "EmailRecognizer",
    "IPAddressRecognizer",
    "OrganizationRecognizer",
    "PersonRecognizer",
    "PhoneRecognizer",
    "Recognizer",
    "SSNRecognizer",
    "all_recognizers",
    "semantic_recognizers",
    "structured_recognizers",
]
