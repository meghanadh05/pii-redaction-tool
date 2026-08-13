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
