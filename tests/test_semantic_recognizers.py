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
