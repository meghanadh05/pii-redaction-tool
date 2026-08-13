"""US SSN recognizer scaffold: shape and invalid-range validation in Phase 2."""

from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


class SSNRecognizer(Recognizer):
    name = "ssn_regex_validated"
    supported_types = frozenset({PIIType.SSN})

    def detect(self, text: str) -> list[PIIEntity]:
        raise NotImplementedError("SSN detection is scheduled for Phase 2")
