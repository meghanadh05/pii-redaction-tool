"""Entity-level exact-match evaluation primitives.

No metrics are emitted until manually labelled ground truth exists. ADDRESS
relaxed-overlap matching and a precisely defined accuracy denominator are
scheduled for Phase 2 alongside the annotation format.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.models import PIIType


@dataclass(frozen=True, slots=True, order=True)
class SpanAnnotation:
    container_id: str
    entity_type: PIIType
    start: int
    end: int

    def __post_init__(self) -> None:
        if not self.container_id.strip():
            raise ValueError("container_id must be non-empty")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("Annotation span must be non-empty")


@dataclass(frozen=True, slots=True)
class MetricCounts:
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def precision(self) -> float:
        denominator = self.true_positives + self.false_positives
        return self.true_positives / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        denominator = self.true_positives + self.false_negatives
        return self.true_positives / denominator if denominator else 0.0

    @property
    def f1(self) -> float:
        denominator = self.precision + self.recall
        return 2 * self.precision * self.recall / denominator if denominator else 0.0

    def to_dict(self) -> dict[str, float | int]:
        return {
            "tp": self.true_positives,
            "fp": self.false_positives,
            "fn": self.false_negatives,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


def exact_match_counts(
    predictions: Iterable[SpanAnnotation],
    ground_truth: Iterable[SpanAnnotation],
) -> MetricCounts:
    """Score unique (container, type, start, end) annotations by exact match."""

    predicted_set = set(predictions)
    truth_set = set(ground_truth)
    return MetricCounts(
        true_positives=len(predicted_set & truth_set),
        false_positives=len(predicted_set - truth_set),
        false_negatives=len(truth_set - predicted_set),
    )


def exact_counts_by_type(
    predictions: Iterable[SpanAnnotation],
    ground_truth: Iterable[SpanAnnotation],
) -> dict[PIIType, MetricCounts]:
    predicted = tuple(predictions)
    truth = tuple(ground_truth)
    return {
        entity_type: exact_match_counts(
            (item for item in predicted if item.entity_type is entity_type),
            (item for item in truth if item.entity_type is entity_type),
        )
        for entity_type in PIIType
    }
