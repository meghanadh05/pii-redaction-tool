"""Address recognizer scaffold: local NER and postal context in Phase 2."""

from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


class AddressRecognizer(Recognizer):
    name = "address_ner_context"
    supported_types = frozenset({PIIType.ADDRESS})

    def detect(self, text: str) -> list[PIIEntity]:
        raise NotImplementedError("Address detection is scheduled for Phase 2")
