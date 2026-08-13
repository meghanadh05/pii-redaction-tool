from __future__ import annotations

from evaluation.evaluate import SpanAnnotation, exact_counts_by_type, exact_match_counts
from src.models import PIIType


def test_exact_metrics_do_not_treat_partial_overlap_as_true_positive() -> None:
    truth = [SpanAnnotation("body/p-12", PIIType.ADDRESS, 10, 30)]
    predictions = [
        SpanAnnotation("body/p-12", PIIType.ADDRESS, 10, 30),
        SpanAnnotation("body/p-12", PIIType.EMAIL, 40, 50),
        SpanAnnotation("body/p-12", PIIType.ADDRESS, 12, 30),
    ]

    metrics = exact_match_counts(predictions, truth)

    assert metrics.true_positives == 1
    assert metrics.false_positives == 2
    assert metrics.false_negatives == 0
    assert metrics.precision == 1 / 3
    assert metrics.recall == 1.0
    assert metrics.f1 == 0.5
    assert metrics.entity_detection_accuracy == 1 / 3


def test_same_offsets_in_different_containers_are_distinct() -> None:
    truth = [SpanAnnotation("body/p-1", PIIType.PERSON, 0, 8)]
    prediction = [SpanAnnotation("header-1/p-1", PIIType.PERSON, 0, 8)]

    metrics = exact_match_counts(prediction, truth)

    assert metrics.true_positives == 0
    assert metrics.false_positives == 1
    assert metrics.false_negatives == 1


def test_per_type_counts_include_required_categories_with_zero_counts() -> None:
    reports = exact_counts_by_type([], [])

    assert set(reports) == set(PIIType)
    assert reports[PIIType.SSN].to_dict() == {
        "tp": 0,
        "fp": 0,
        "fn": 0,
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
        "entity_detection_accuracy": None,
    }
