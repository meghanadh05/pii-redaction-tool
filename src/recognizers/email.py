"""Email recognizer scaffold: regex plus domain/syntax safeguards in Phase 2."""

from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


class EmailRecognizer(Recognizer):
    name = "email_regex"
    supported_types = frozenset({PIIType.EMAIL})

    def detect(self, text: str) -> list[PIIEntity]:
        raise NotImplementedError("Email detection is scheduled for Phase 2")
