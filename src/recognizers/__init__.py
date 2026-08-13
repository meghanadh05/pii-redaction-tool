"""PII recognizers and the Phase 2A structured recognizer set."""

from .base import Recognizer
from .credit_card import CreditCardRecognizer
from .dob import DOBRecognizer
from .email import EmailRecognizer
from .ip_address import IPAddressRecognizer
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


__all__ = [
    "CreditCardRecognizer",
    "DOBRecognizer",
    "EmailRecognizer",
    "IPAddressRecognizer",
    "PhoneRecognizer",
    "Recognizer",
    "SSNRecognizer",
    "structured_recognizers",
]
