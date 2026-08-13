from __future__ import annotations

from dataclasses import dataclass

from src.detector import DetectionEngine
from src.local_nlp import LocalSpacyProvider, NERSpan
from src.models import PIIType
from src.recognizers.address import AddressRecognizer
from src.recognizers.organization import OrganizationRecognizer
from src.recognizers.person import PersonRecognizer


@dataclass(frozen=True)
class FixedProvider:
    spans: tuple[NERSpan, ...] = ()

    def entities(self, text: str) -> tuple[NERSpan, ...]:
        return self.spans


def test_person_splits_slash_separated_names_even_when_ner_calls_list_org() -> None:
    text = "Alice Smith/ Priya Shah"
    recognizer = PersonRecognizer(FixedProvider((NERSpan("ORG", 0, len(text)),)))

    results = recognizer.detect(text)

    assert [(item.text, item.start, item.end) for item in results] == [
        ("Alice Smith", 0, 11),
        ("Priya Shah", 13, 23),
    ]
    assert all(item.entity_type is PIIType.PERSON for item in results)


def test_generic_capitalized_phrase_is_not_accepted_as_person() -> None:
    text = "Board of Directors"
    recognizer = PersonRecognizer(FixedProvider((NERSpan("PERSON", 0, len(text)),)))

    assert recognizer.detect(text) == []


def test_person_role_context_recovers_an_org_mislabel() -> None:
    text = "The appointed engineer, namely Alice Maria Smith"
    start = text.index("Alice")
    recognizer = PersonRecognizer(FixedProvider((NERSpan("ORG", start, len(text)),)))

    results = recognizer.detect(text)

    assert len(results) == 1
    assert results[0].text == "Alice Maria Smith"
    assert results[0].metadata["strong_context"] is True


def test_company_legal_suffix_handles_uppercase_tabs_and_formerly_boundary() -> None:
    provider = FixedProvider()
    recognizer = OrganizationRecognizer(provider)

    uppercase = recognizer.detect("EXAMPLE INTERNATIONAL LIMITED")
    tabbed = recognizer.detect("Example\tSecurities Limited")
    formerly = recognizer.detect("(Formerly Old Example Private Limited)")

    assert [item.text for item in uppercase] == ["EXAMPLE INTERNATIONAL LIMITED"]
    assert [item.text for item in tabbed] == ["Example\tSecurities Limited"]
    assert [item.text for item in formerly] == ["Old Example Private Limited"]


def test_corporate_heading_and_role_words_are_not_automatically_companies() -> None:
    for text in ("REGISTRAR TO THE OFFER", "Audit Committee", "Company"):
        recognizer = OrganizationRecognizer(
            FixedProvider((NERSpan("ORG", 0, len(text)),))
        )
        assert recognizer.detect(text) == []


def test_address_requires_postal_structure_not_a_location_alone() -> None:
    recognizer = AddressRecognizer(FixedProvider((NERSpan("GPE", 0, len("Mumbai")),)))

    assert recognizer.detect("Mumbai") == []
    address = "Registered Office: 12, Example Road, Mumbai 400001, India;"
    results = recognizer.detect(address)
    assert len(results) == 1
    assert results[0].text == "12, Example Road, Mumbai 400001, India"


def test_precision_negative_identifiers_and_ordinary_date_produce_no_semantic_pii() -> (
    None
):
    engine = DetectionEngine(
        [
            PersonRecognizer(FixedProvider()),
            OrganizationRecognizer(FixedProvider()),
            AddressRecognizer(FixedProvider()),
        ]
    )

    for text in (
        "December 10, 2025",
        "₹4,200.00 million",
        "SEBI Registration Number: INM000013004",
        "CIN: U67190MH1999PTC118368",
        "DIN: 01234567",
        "page 250",
    ):
        assert engine.detect(text) == []


def test_installed_spacy_model_runs_locally_on_python_313_environment() -> None:
    provider = LocalSpacyProvider()
    entities = provider.entities("Alice Smith works at Example Limited in Mumbai.")
    versions = provider.model_versions()

    assert {item.label for item in entities} >= {"PERSON", "ORG", "GPE"}
    assert versions["spacy"] == "3.8.15"
    assert versions["model_version"] == "3.8.0"


def test_company_context_is_local_not_paragraph_wide() -> None:
    text = (
        "Our Company signed the agreement with the Book Running Lead Managers "
        "under the Securities and Exchange Board of India Regulations."
    )
    phrases = (
        "Book Running Lead Managers",
        "Securities and Exchange Board of India Regulations",
    )
    spans = tuple(
        NERSpan("ORG", text.index(value), text.index(value) + len(value))
        for value in phrases
    )

    assert OrganizationRecognizer(FixedProvider(spans)).detect(text) == []


def test_company_legal_suffixes_split_adjacent_names_and_trim_role_prefix() -> None:
    text = (
        "Escrow Collection Bank Aurora Bank Limited and "
        "Cedar Securities Private Limited"
    )

    results = OrganizationRecognizer(FixedProvider()).detect(text)

    assert [item.text for item in results] == [
        "Aurora Bank Limited",
        "Cedar Securities Private Limited",
    ]


def test_company_local_label_can_accept_professional_firm_without_suffix() -> None:
    text = "The statutory auditor, namely Rao & Menon Associates, issued a report."
    value = "Rao & Menon Associates"
    start = text.index(value)

    results = OrganizationRecognizer(
        FixedProvider((NERSpan("ORG", start, start + len(value)),))
    ).detect(text)

    assert [item.text for item in results] == [value]


def test_company_rejects_government_regulations_trusts_roles_and_person_like_orgs() -> (
    None
):
    cases = (
        "Ministry of Trade and Industry",
        "Securities Market Regulations 2024",
        "Evergreen Family Trust",
        "Anchor Investors",
        "Kavya Rao",
    )
    for value in cases:
        text = f"Our Company refers to {value} in this section."
        start = text.index(value)
        recognizer = OrganizationRecognizer(
            FixedProvider((NERSpan("ORG", start, start + len(value)),))
        )
        assert recognizer.detect(text) == []


def test_person_role_list_extracts_uppercase_comma_slash_and_final_names() -> None:
    text = (
        "Our Promoters: AARAV MEHTA, PRIYA NAIR / ISHAAN RAO and "
        "KAVYA SHAH. Further details follow."
    )

    results = PersonRecognizer(FixedProvider()).detect(text)

    assert [item.text for item in results] == [
        "AARAV MEHTA",
        "PRIYA NAIR",
        "ISHAAN RAO",
        "KAVYA SHAH",
    ]


def test_person_org_mislabel_requires_local_role_evidence() -> None:
    text = "The whole-time director being Ananya Kulkarni signed the report."
    value = "Ananya Kulkarni"
    start = text.index(value)
    provider = FixedProvider((NERSpan("ORG", start, start + len(value)),))

    assert [item.text for item in PersonRecognizer(provider).detect(text)] == [value]

    distant = f"Director responsibilities are described here. {value} appears later."
    distant_start = distant.index(value)
    distant_provider = FixedProvider(
        (NERSpan("ORG", distant_start, distant_start + len(value)),)
    )
    assert PersonRecognizer(distant_provider).detect(distant) == []


def test_person_rejects_capitalized_address_and_institution_phrases() -> None:
    for value in ("Sunrise Business Centre", "National Audit Committee"):
        recognizer = PersonRecognizer(
            FixedProvider((NERSpan("PERSON", 0, len(value)),))
        )
        assert recognizer.detect(value) == []


def test_address_supports_fewer_commas_and_stops_before_contact_fields() -> None:
    text = (
        "Registered Office: Flat 12 Sunrise Road East Pune 411001, India "
        "Telephone: +91 20 5555 0101 Email: contact@example.com"
    )

    results = AddressRecognizer(FixedProvider()).detect(text)

    assert [item.text for item in results] == [
        "Flat 12 Sunrise Road East Pune 411001, India"
    ]


def test_address_embedded_in_prose_and_no_postcode_structural_address() -> None:
    embedded = (
        "The facility is located at Plot 8, Meridian Industrial Estate, "
        "Nashik 422010, Maharashtra, India."
    )
    no_postcode = "Operations Office: Tower 3, Example Tech Campus, B-2 Level"

    assert [
        item.text for item in AddressRecognizer(FixedProvider()).detect(embedded)
    ] == ["Plot 8, Meridian Industrial Estate, Nashik 422010, Maharashtra, India"]
    assert [
        item.text for item in AddressRecognizer(FixedProvider()).detect(no_postcode)
    ] == ["Tower 3, Example Tech Campus, B-2 Level"]


def test_address_trims_company_prefix_and_rejects_location_only() -> None:
    text = "Example Advisory LLP Flat 4, Cedar Road, Pune 411002, India"
    company = "Example Advisory LLP"
    provider = FixedProvider((NERSpan("ORG", 0, len(company)),))

    results = AddressRecognizer(provider).detect(text)

    assert [item.text for item in results] == ["Flat 4, Cedar Road, Pune 411002, India"]
    assert AddressRecognizer(FixedProvider()).detect("Pune, Maharashtra, India") == []
