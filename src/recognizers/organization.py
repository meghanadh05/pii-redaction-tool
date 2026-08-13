"""Company recognizer scaffold: local NER plus legal-suffix rules in Phase 2."""

from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


class OrganizationRecognizer(Recognizer):
    name = "company_ner_context"
    supported_types = frozenset({PIIType.COMPANY})

    def detect(self, text: str) -> list[PIIEntity]:
        raise NotImplementedError("Company detection is scheduled for Phase 2")
