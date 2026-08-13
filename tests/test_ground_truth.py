from pathlib import Path

from evaluation.dataset import load_ground_truth


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_development_ground_truth_matches_frozen_source_and_extractor() -> None:
    dataset = load_ground_truth(
        PROJECT_ROOT / "evaluation" / "ground_truth" / "development",
        source_path=PROJECT_ROOT / "input" / "Red Herring Prospectus.docx",
    )

    distribution = dataset.distribution()
    assert distribution["reviewed_container_count"] == 53
    assert distribution["annotation_count"] == 44
    assert distribution["annotations_by_type"] == {
        "PERSON": 14,
        "EMAIL": 6,
        "PHONE": 5,
        "COMPANY": 13,
        "ADDRESS": 6,
        "SSN": 0,
        "CREDIT_CARD": 0,
        "DOB": 0,
        "IP_ADDRESS": 0,
    }


def test_holdout_is_larger_complete_and_disjoint_from_development() -> None:
    source = PROJECT_ROOT / "input" / "Red Herring Prospectus.docx"
    development = load_ground_truth(
        PROJECT_ROOT / "evaluation" / "ground_truth" / "development",
        source_path=source,
    )
    holdout = load_ground_truth(
        PROJECT_ROOT / "evaluation" / "ground_truth" / "holdout",
        source_path=source,
    )

    distribution = holdout.distribution()
    assert holdout.container_ids.isdisjoint(development.container_ids)
    assert distribution["reviewed_container_count"] == 120
    assert distribution["annotation_count"] == 101
    assert distribution["annotations_by_type"] == {
        "PERSON": 34,
        "EMAIL": 19,
        "PHONE": 5,
        "COMPANY": 24,
        "ADDRESS": 19,
        "SSN": 0,
        "CREDIT_CARD": 0,
        "DOB": 0,
        "IP_ADDRESS": 0,
    }
    assert distribution["containers_by_stratum"] == {
        "address_variant": 15,
        "capitalized_heading": 8,
        "company_heavy": 40,
        "contact_structured": 15,
        "financial_legal_negative": 15,
        "management_person": 20,
        "textbox": 7,
    }
