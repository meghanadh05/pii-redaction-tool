"""Phone recognizer scaffold: normalized/context-aware validation in Phase 2."""

from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


class PhoneRecognizer(Recognizer):
    name = "phone_regex_context"
    supported_types = frozenset({PIIType.PHONE})

    def detect(self, text: str) -> list[PIIEntity]:
        raise NotImplementedError("Phone detection is scheduled for Phase 2")
