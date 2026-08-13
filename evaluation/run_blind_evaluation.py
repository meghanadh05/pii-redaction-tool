"""Run the single blind evaluation against a frozen, never-tuned dataset.

Unlike ``run_development``, this reports a dataset whose labels were written
after the recognizers were frozen and which has never informed a repair. It is
intended to be run once per recognizer snapshot; the result is written to an
append-only, commit-qualified artifact rather than overwritten.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

from evaluation.dataset import GroundTruthDataset, load_ground_truth
from evaluation.evaluate import SpanAnnotation, error_counts, evaluate_predictions
from src.detector import DetectionEngine
from src.docx_processor import extract_text_containers
from src.local_nlp import LocalSpacyProvider
from src.recognizers import all_recognizers


def _recognizer_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def build_blind_report(
    dataset: GroundTruthDataset,
    *,
    source_path: Path,
) -> dict[str, object]:
    """Evaluate every exhaustively reviewed container and omit source text."""

    containers = {
        item.id: item
        for item in extract_text_containers(source_path)
        if item.id in dataset.container_ids
    }
    missing = dataset.container_ids - set(containers)
    if missing:
        raise ValueError(f"{len(missing)} annotated containers are missing from source")

    detector = DetectionEngine(all_recognizers())
    predictions = tuple(
        SpanAnnotation(
            container_id=container_id,
            entity_type=entity.entity_type,
            start=entity.start,
            end=entity.end,
        )
        for container_id in sorted(dataset.container_ids)
        for entity in detector.detect(containers[container_id].text)
    )
    metrics = evaluate_predictions(predictions, dataset.annotations)
    return {
        "report_schema_version": "1.0",
        "dataset_role": "blind_final_evaluation_single_run",
        "privacy_safe": True,
        "document_sha256": dataset.document_sha256,
        "extraction_version": dataset.extraction_version,
        "recognizer_commit": _recognizer_commit(),
        "local_nlp": LocalSpacyProvider().model_versions(),
        "sample": dataset.distribution(),
        "prediction_count": len(predictions),
        "metrics": metrics.to_dict(),
        "error_analysis": error_counts(predictions, dataset.annotations),
        "interpretation_limits": (
            "Labels for this dataset were written after the recognizers were "
            "frozen and have never informed a repair, so these are held-out "
            "results. The sample is risk-stratified rather than uniformly "
            "sampled, so it is not an unbiased prevalence estimate for every "
            "paragraph. The annotator had prior exposure to the recognizer "
            "implementation, so COMPANY and ADDRESS boundary conventions may "
            "be biased toward the detector; exact and relaxed ADDRESS results "
            "are both reported so that effect stays visible."
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_path", type=Path)
    parser.add_argument("dataset_directory", type=Path)
    arguments = parser.parse_args(argv)
    dataset = load_ground_truth(
        arguments.dataset_directory,
        source_path=arguments.source_path,
    )
    print(
        json.dumps(
            build_blind_report(dataset, source_path=arguments.source_path),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
