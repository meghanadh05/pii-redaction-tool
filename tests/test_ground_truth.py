import json
from collections import Counter
from hashlib import sha256
from pathlib import Path

from evaluation.dataset import load_ground_truth
from src.docx_processor import EXTRACTOR_SCHEMA_VERSION, extract_text_containers


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = PROJECT_ROOT / "input" / "Red Herring Prospectus.docx"


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
    source = SOURCE_PATH
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

    initial_report = json.loads(
        (PROJECT_ROOT / "docs" / "phase2c_holdout_initial_75ce5f8.json").read_text()
    )
    assert initial_report["immutable_result_name"] == (
        "phase2c_holdout_initial_75ce5f8"
    )
    assert initial_report["recognizer_snapshot_commit"] == "75ce5f8"
    assert initial_report["holdout_snapshot_commit"] == "bc1fe79"
    assert initial_report["sample"] == distribution


def test_phase2c_initial_result_remains_byte_for_byte_frozen() -> None:
    initial_result = PROJECT_ROOT / "docs" / "phase2c_holdout_initial_75ce5f8.json"

    assert sha256(initial_result.read_bytes()).hexdigest() == (
        "72f7dfdcf861f8b4fa329531745727892f83d7a3ddffdf7b467724b857c5bcf8"
    )


def test_final_candidate_pool_is_frozen_annotated_and_disjoint() -> None:
    development = load_ground_truth(
        PROJECT_ROOT / "evaluation" / "ground_truth" / "development",
        source_path=SOURCE_PATH,
    )
    phase2c_holdout = load_ground_truth(
        PROJECT_ROOT / "evaluation" / "ground_truth" / "holdout",
        source_path=SOURCE_PATH,
    )
    pool_directory = (
        PROJECT_ROOT / "evaluation" / "ground_truth" / "final_candidate_pool"
    )
    manifest = json.loads((pool_directory / "manifest.json").read_text())
    selected = manifest["containers"]
    selected_ids = [item["container_id"] for item in selected]

    assert manifest["document_sha256"] == sha256(SOURCE_PATH.read_bytes()).hexdigest()
    assert manifest["extraction_version"] == EXTRACTOR_SCHEMA_VERSION == "1.0"
    assert manifest["recognizer_snapshot_commit"] == "99f9fb5"
    # The pool was selected and frozen while unlabelled, then annotated once
    # against fixed written conventions and scored exactly once.
    assert manifest["annotation_status"] == "complete"
    assert manifest["labels_inspected"] is True
    assert manifest["pool_container_count"] == len(selected_ids) == 180
    assert len(selected_ids) == len(set(selected_ids))
    assert all(item["review_complete"] is True for item in selected)
    assert (pool_directory / "annotation_conventions.md").is_file()
    assert set(selected_ids).isdisjoint(development.container_ids)
    assert set(selected_ids).isdisjoint(phase2c_holdout.container_ids)
    assert set(selected_ids) <= {
        item.id for item in extract_text_containers(SOURCE_PATH)
    }
    assert Counter(item["sample_stratum"] for item in selected) == {
        "address_variant": 25,
        "capitalized_heading_negative": 15,
        "company_legal_prose": 40,
        "contact_structured": 20,
        "financial_legal_negative": 25,
        "general_unlabelled_candidate": 5,
        "management_person": 35,
        "textbox": 15,
    }
    canonical = "\n".join(
        f"{item['container_id']}\t{item['sample_stratum']}" for item in selected
    )
    assert sha256(canonical.encode()).hexdigest() == manifest["pool_manifest_sha256"]
    assert manifest["pool_manifest_sha256"] == (
        "ceefe99f45589f911c8b634f85ed9f21a99ae48337013398554e55fa2c6307b9"
    )


def test_blind_pool_annotations_are_valid_and_confined_to_the_pool() -> None:
    pool_directory = (
        PROJECT_ROOT / "evaluation" / "ground_truth" / "final_candidate_pool"
    )
    dataset = load_ground_truth(pool_directory, source_path=SOURCE_PATH)
    containers = {
        item.id: item.text
        for item in extract_text_containers(SOURCE_PATH)
        if item.id in dataset.container_ids
    }

    assert len(dataset.annotations) == 168
    assert {item.container_id for item in dataset.annotations} <= dataset.container_ids

    seen: dict[str, list[tuple[int, int]]] = {}
    for annotation in dataset.annotations:
        text = containers[annotation.container_id]
        assert 0 <= annotation.start < annotation.end <= len(text)
        assert text[annotation.start : annotation.end].strip()
        for previous in seen.setdefault(annotation.container_id, []):
            assert annotation.start >= previous[1] or annotation.end <= previous[0]
        seen[annotation.container_id].append((annotation.start, annotation.end))
