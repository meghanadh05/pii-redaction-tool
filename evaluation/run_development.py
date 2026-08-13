"""Run the privacy-safe Phase 2B development-set evaluation."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from evaluation.dataset import GroundTruthDataset, load_ground_truth
from evaluation.evaluate import (
    SpanAnnotation,
    error_counts,
    evaluate_predictions,
)
from src.detector import DetectionEngine
from src.docx_processor import extract_text_containers
from src.local_nlp import LocalSpacyProvider
from src.recognizers import all_recognizers


def build_development_report(
    dataset: GroundTruthDataset,
    *,
    source_path: Path,
) -> dict[str, object]:
    """Evaluate only exhaustively reviewed containers and omit source text."""

    containers = {
        item.id: item
        for item in extract_text_containers(source_path)
        if item.id in dataset.container_ids
    }
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
        "dataset_role": "development_calibration_not_final_evaluation",
        "privacy_safe": True,
        "document_sha256": dataset.document_sha256,
        "extraction_version": dataset.extraction_version,
        "local_nlp": LocalSpacyProvider().model_versions(),
        "sample": dataset.distribution(),
        "prediction_count": len(predictions),
        "metrics": metrics.to_dict(),
        "error_analysis": error_counts(predictions, dataset.annotations),
        "interpretation_limits": (
            "This small labelled subset was used to calibrate semantic rules. "
            "Its metrics are development results and must not be presented as "
            "held-out or final-document performance."
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
            build_development_report(dataset, source_path=arguments.source_path),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
