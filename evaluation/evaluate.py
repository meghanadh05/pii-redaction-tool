"""Entity-level exact and relaxed evaluation primitives."""

from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
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

    @property
    def entity_detection_accuracy(self) -> float | None:
        """Exact entity-set accuracy (Jaccard), without inflated true negatives."""

        denominator = self.true_positives + self.false_positives + self.false_negatives
        return self.true_positives / denominator if denominator else None

    def to_dict(self) -> dict[str, float | int | None]:
        return {
            "tp": self.true_positives,
            "fp": self.false_positives,
            "fn": self.false_negatives,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "entity_detection_accuracy": self.entity_detection_accuracy,
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


def _overlap_ratio(left: SpanAnnotation, right: SpanAnnotation) -> float:
    overlap = max(0, min(left.end, right.end) - max(left.start, right.start))
    return overlap / min(left.end - left.start, right.end - right.start)


def relaxed_overlap_counts(
    predictions: Iterable[SpanAnnotation],
    ground_truth: Iterable[SpanAnnotation],
    *,
    entity_type: PIIType = PIIType.ADDRESS,
    minimum_overlap: float = 0.5,
) -> MetricCounts:
    """One-to-one relaxed matching within a container and entity category.

    A pair qualifies when its intersection covers at least ``minimum_overlap``
    of the shorter span. Candidate pairs are greedily selected by greatest
    overlap and then smallest boundary error. This tolerates address boundary
    differences without allowing one broad prediction to match many labels.
    """

    if not 0.0 < minimum_overlap <= 1.0:
        raise ValueError("minimum_overlap must be in (0, 1]")
    predicted = tuple(
        item for item in set(predictions) if item.entity_type is entity_type
    )
    truth = tuple(item for item in set(ground_truth) if item.entity_type is entity_type)
    candidates: list[tuple[float, int, int, int]] = []
    for prediction_index, prediction in enumerate(predicted):
        for truth_index, expected in enumerate(truth):
            if prediction.container_id != expected.container_id:
                continue
            ratio = _overlap_ratio(prediction, expected)
            if ratio >= minimum_overlap:
                boundary_error = abs(prediction.start - expected.start) + abs(
                    prediction.end - expected.end
                )
                candidates.append(
                    (-ratio, boundary_error, prediction_index, truth_index)
                )

    matched_predictions: set[int] = set()
    matched_truth: set[int] = set()
    for _, _, prediction_index, truth_index in sorted(candidates):
        if prediction_index in matched_predictions or truth_index in matched_truth:
            continue
        matched_predictions.add(prediction_index)
        matched_truth.add(truth_index)
    return MetricCounts(
        true_positives=len(matched_truth),
        false_positives=len(predicted) - len(matched_predictions),
        false_negatives=len(truth) - len(matched_truth),
    )


@dataclass(frozen=True, slots=True)
class MacroMetrics:
    included_type_count: int
    precision: float
    recall: float
    f1: float
    entity_detection_accuracy: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "included_type_count": self.included_type_count,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "entity_detection_accuracy": self.entity_detection_accuracy,
        }


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    exact_micro: MetricCounts
    exact_by_type: dict[PIIType, MetricCounts]
    exact_macro_ground_truth_types: MacroMetrics
    relaxed_address: MetricCounts
    relaxed_address_minimum_overlap: float

    def to_dict(self) -> dict[str, object]:
        return {
            "matching_policy": {
                "primary": "exact_container_type_span",
                "address_relaxed": "one_to_one_intersection_over_shorter_span",
                "address_relaxed_minimum_overlap": self.relaxed_address_minimum_overlap,
                "accuracy_definition": "entity_set_jaccard_tp_over_tp_fp_fn",
            },
            "exact": {
                "micro": self.exact_micro.to_dict(),
                "macro_ground_truth_types": self.exact_macro_ground_truth_types.to_dict(),
                "by_type": {
                    entity_type.value: self.exact_by_type[entity_type].to_dict()
                    for entity_type in PIIType
                },
            },
            "address_relaxed": self.relaxed_address.to_dict(),
        }


def evaluate_predictions(
    predictions: Iterable[SpanAnnotation],
    ground_truth: Iterable[SpanAnnotation],
    *,
    address_minimum_overlap: float = 0.5,
) -> EvaluationReport:
    """Calculate exact per-type/micro/macro and relaxed ADDRESS metrics."""

    predicted = tuple(predictions)
    truth = tuple(ground_truth)
    exact_by_type = exact_counts_by_type(predicted, truth)
    truth_types = {item.entity_type for item in truth}
    macro_source = [
        exact_by_type[entity_type]
        for entity_type in sorted(truth_types, key=lambda item: item.value)
    ]
    if not macro_source:
        raise ValueError("Macro metrics require at least one ground-truth entity")
    accuracy_values = [
        counts.entity_detection_accuracy
        for counts in macro_source
        if counts.entity_detection_accuracy is not None
    ]
    macro = MacroMetrics(
        included_type_count=len(macro_source),
        precision=sum(item.precision for item in macro_source) / len(macro_source),
        recall=sum(item.recall for item in macro_source) / len(macro_source),
        f1=sum(item.f1 for item in macro_source) / len(macro_source),
        entity_detection_accuracy=sum(accuracy_values) / len(accuracy_values),
    )
    return EvaluationReport(
        exact_micro=exact_match_counts(predicted, truth),
        exact_by_type=exact_by_type,
        exact_macro_ground_truth_types=macro,
        relaxed_address=relaxed_overlap_counts(
            predicted,
            truth,
            entity_type=PIIType.ADDRESS,
            minimum_overlap=address_minimum_overlap,
        ),
        relaxed_address_minimum_overlap=address_minimum_overlap,
    )


def error_counts(
    predictions: Iterable[SpanAnnotation],
    ground_truth: Iterable[SpanAnnotation],
) -> dict[str, dict[str, int]]:
    """Return a privacy-safe FP/FN type distribution."""

    predicted_set = set(predictions)
    truth_set = set(ground_truth)
    false_positives: defaultdict[str, int] = defaultdict(int)
    false_negatives: defaultdict[str, int] = defaultdict(int)
    for item in predicted_set - truth_set:
        false_positives[item.entity_type.value] += 1
    for item in truth_set - predicted_set:
        false_negatives[item.entity_type.value] += 1
    return {
        "false_positives_by_type": dict(sorted(false_positives.items())),
        "false_negatives_by_type": dict(sorted(false_negatives.items())),
    }
