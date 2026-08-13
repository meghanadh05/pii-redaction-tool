"""Person recognizer scaffold: local NER plus document context in Phase 2."""

from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


class PersonRecognizer(Recognizer):
    name = "person_ner_context"
    supported_types = frozenset({PIIType.PERSON})

    def detect(self, text: str) -> list[PIIEntity]:
        raise NotImplementedError("Person detection is scheduled for Phase 2")
