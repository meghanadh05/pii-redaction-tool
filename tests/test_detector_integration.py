from __future__ import annotations

import json

from src.detector import DetectionEngine
from src.docx_processor import StoryKind, TextContainer
from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer
from src.recognizers.credit_card import CreditCardRecognizer
from src.recognizers.dob import DOBRecognizer
from src.recognizers.email import EmailRecognizer
from src.recognizers.phone import PhoneRecognizer
from src.reporting import detect_containers


class WeakPersonRecognizer(Recognizer):
    name = "weak_person"
    supported_types = frozenset({PIIType.PERSON})

    def __init__(self, start: int, end: int) -> None:
        self.start = start
        self.end = end

    def detect(self, text: str) -> list[PIIEntity]:
        return [
            PIIEntity(
                PIIType.PERSON,
                text[self.start : self.end],
                self.start,
                self.end,
                0.999,
                self.name,
            )
        ]


def test_real_email_recognizer_beats_overlapping_weak_detection() -> None:
    text = "user@example.test"
    engine = DetectionEngine([WeakPersonRecognizer(0, 4), EmailRecognizer()])

    assert [entity.entity_type for entity in engine.detect(text)] == [PIIType.EMAIL]


def test_luhn_card_beats_overlapping_phone_candidate() -> None:
    text = "+4222222222222"
    engine = DetectionEngine([PhoneRecognizer(), CreditCardRecognizer()])

    result = engine.detect(text)

    assert len(result) == 1
    assert result[0].entity_type is PIIType.CREDIT_CARD


def test_contextual_dob_beats_overlapping_weak_date_span() -> None:
    text = "DOB: 12 May 1988"
    date_start = text.index("12 May")
    engine = DetectionEngine(
        [WeakPersonRecognizer(date_start, len(text)), DOBRecognizer()]
    )

    result = engine.detect(text)

    assert len(result) == 1
    assert result[0].entity_type is PIIType.DOB


def test_reporting_is_privacy_safe_unless_explicitly_unsafe() -> None:
    from docx import Document

    raw_value = "person@example.test"
    paragraph = Document().add_paragraph(f"Contact {raw_value}")
    container = TextContainer.from_paragraph(
        paragraph,
        container_id="body/p0000",
        story_type=StoryKind.BODY_PARAGRAPH,
    )
    report = detect_containers((container,), source_name="synthetic.docx")

    safe_json = json.dumps(report.to_dict())
    unsafe_json = json.dumps(report.to_dict(unsafe_show_pii=True))

    assert raw_value not in safe_json
    assert raw_value in unsafe_json
    assert report.summary()["accepted_detection_count"] == 1
