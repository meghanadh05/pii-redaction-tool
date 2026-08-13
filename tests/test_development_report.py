from __future__ import annotations

import json
from pathlib import Path

from evaluation.dataset import load_ground_truth
from evaluation.run_development import build_development_report
from src.detector import DetectionEngine
from src.docx_audit import audit_shape_metadata
from src.recognizers import all_recognizers


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT_ROOT / "input" / "Red Herring Prospectus.docx"


def test_committed_development_report_is_reproducible_and_privacy_safe() -> None:
    dataset = load_ground_truth(
        PROJECT_ROOT / "evaluation" / "ground_truth" / "development",
        source_path=SOURCE,
    )
    expected = json.loads(
        (PROJECT_ROOT / "docs" / "phase2b_development_report.json").read_text()
    )

    actual = build_development_report(dataset, source_path=SOURCE)

    assert actual == expected
    serialized = json.dumps(actual)
    assert '"text"' not in serialized
    assert '"normalized"' not in serialized


def test_committed_shape_audit_is_reproducible_and_privacy_safe() -> None:
    expected = json.loads(
        (PROJECT_ROOT / "docs" / "phase2b_shape_audit.json").read_text()
    )
    detector = DetectionEngine(all_recognizers())

    actual = audit_shape_metadata(SOURCE, detector=detector).to_dict()

    assert actual == expected
    assert actual["privacy_safe"] is True
    assert actual["automatically_rewritten"] is False
