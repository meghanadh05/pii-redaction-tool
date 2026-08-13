from __future__ import annotations

import pytest

from src.recognizers.credit_card import CreditCardRecognizer
from src.recognizers.dob import DOBRecognizer
from src.recognizers.email import EmailRecognizer
from src.recognizers.ip_address import IPAddressRecognizer
from src.recognizers.phone import PhoneRecognizer
from src.recognizers.ssn import SSNRecognizer


@pytest.mark.parametrize(
    "value",
    [
        "first.last@example.com",
        "user+alias@sub.example.co.in",
        "UPPER.CASE@EXAMPLE.COM",
    ],
)
def test_email_accepts_practical_valid_forms(value: str) -> None:
    entities = EmailRecognizer().detect(f"Contact ({value}), please.")

    assert [entity.text for entity in entities] == [value]
    assert entities[0].metadata["normalized"] == value.casefold()
    assert entities[0].confidence == 0.99


@pytest.mark.parametrize(
    "value",
    [
        "plainaddress",
        "a..b@example.com",
        "user@example",
        "user@-example.com",
        "user@example..com",
        "https://user@example.com/profile",
    ],
)
def test_email_rejects_invalid_forms_and_url_userinfo(value: str) -> None:
    assert EmailRecognizer().detect(value) == []


@pytest.mark.parametrize(
    ("value", "expected_normalized"),
    [
        ("+91 9876543210", "+919876543210"),
        ("+91 98765 43210", "+919876543210"),
        ("+91-98765-43210", "+919876543210"),
        ("9876543210", "+919876543210"),
        ("+91 22 4009 4400", "+912240094400"),
        ("020 4505 3237", "02045053237"),
    ],
)
def test_phone_accepts_required_indian_forms(
    value: str, expected_normalized: str
) -> None:
    entities = PhoneRecognizer().detect(value)

    assert len(entities) == 1
    assert entities[0].metadata["normalized"] == expected_normalized


def test_phone_supports_labelled_non_indian_number() -> None:
    value = "(212) 555-0198"
    entities = PhoneRecognizer().detect(f"Telephone: {value}")

    assert [entity.text for entity in entities] == [value]


@pytest.mark.parametrize(
    "text",
    [
        "KSH International Limited",
        "CIN: U28129PN1979PLC141032",
        "SEBI Registration Number: INM000013004",
        "DIN: 00114193",
        "₹4,200.00 million",
        "₹2,900.00 million",
        "December 10, 2025",
        "March 31, 2025",
        "page 250",
        "100% Book Built Offer",
        "123 456 7890",
        "Reference: 987654321012",
    ],
)
def test_phone_rejects_false_positive_examples(text: str) -> None:
    assert PhoneRecognizer().detect(text) == []


def test_ssn_accepts_canonical_shape() -> None:
    entity = SSNRecognizer().detect("SSN: 123-45-6789")[0]

    assert entity.text == "123-45-6789"
    assert entity.metadata["validated"] is True


@pytest.mark.parametrize(
    "value",
    [
        "000-12-3456",
        "666-12-3456",
        "900-12-3456",
        "123-00-3456",
        "123-45-0000",
        "078-05-1120",
        "123 45 6789",
    ],
)
def test_ssn_rejects_invalid_or_noncanonical_values(value: str) -> None:
    assert SSNRecognizer().detect(value) == []


@pytest.mark.parametrize(
    "value",
    ["4111 1111 1111 1111", "5555-5555-5555-4444", "4222222222222"],
)
def test_credit_card_requires_valid_luhn(value: str) -> None:
    entities = CreditCardRecognizer().detect(value)

    assert len(entities) == 1
    assert entities[0].metadata["normalized"] == "".join(value.replace("-", "").split())


@pytest.mark.parametrize(
    "text",
    [
        "4111 1111 1111 1112",
        "DIN: 4222222222222",
        "CIN: 4222222222222",
        "Reference: 1234567890123456",
        "₹4,200.00 million",
    ],
)
def test_credit_card_rejects_luhn_failures_and_identifier_context(text: str) -> None:
    assert CreditCardRecognizer().detect(text) == []


@pytest.mark.parametrize(
    ("value", "normalized"),
    [
        ("192.0.2.4", "192.0.2.4"),
        ("2001:0db8:0000:0000:0000:0000:0000:0001", "2001:db8::1"),
        ("2001:db8::1", "2001:db8::1"),
    ],
)
def test_ip_address_uses_standard_library_validation(
    value: str, normalized: str
) -> None:
    entities = IPAddressRecognizer().detect(value)

    assert len(entities) == 1
    assert entities[0].metadata["normalized"] == normalized


@pytest.mark.parametrize("value", ["999.999.1.1", "256.1.1.1", "1.2.3"])
def test_ip_address_rejects_invalid_values(value: str) -> None:
    assert IPAddressRecognizer().detect(value) == []


@pytest.mark.parametrize(
    ("text", "normalized"),
    [
        ("DOB: 12/05/1988", "1988-05-12"),
        ("Date of Birth: 12-05-1988", "1988-05-12"),
        ("Birth Date: 12 May 1988", "1988-05-12"),
        ("Born: May 12, 1988", "1988-05-12"),
        ("Born on 1988-05-12", "1988-05-12"),
        ("12 May 1988 (DOB)", "1988-05-12"),
        ("D.O.B. 12 May 1988", "1988-05-12"),
    ],
)
def test_dob_requires_and_records_birth_context(text: str, normalized: str) -> None:
    entities = DOBRecognizer().detect(text)

    assert len(entities) == 1
    assert entities[0].metadata["normalized"] == normalized


@pytest.mark.parametrize(
    "text",
    [
        "Dated December 10, 2025",
        "Offer closes December 18, 2025",
        "Financial year ended March 31, 2025",
        "Incorporated July 30, 1979",
        "Board meeting May 6, 2025",
        "12 May 1988",
        "DOB: 31/02/1988",
        "DOB: 12/05/2099",
    ],
)
def test_dob_rejects_ordinary_invalid_and_future_dates(text: str) -> None:
    assert DOBRecognizer().detect(text) == []
