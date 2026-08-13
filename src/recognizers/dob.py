"""DOB recognizer scaffold: dates require explicit birth context in Phase 2."""

from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


class DOBRecognizer(Recognizer):
    name = "dob_context"
    supported_types = frozenset({PIIType.DOB})

    def detect(self, text: str) -> list[PIIEntity]:
        raise NotImplementedError("DOB detection is scheduled for Phase 2")
