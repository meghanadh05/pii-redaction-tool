"""Credit-card recognizer scaffold: candidate regex plus Luhn in Phase 2."""

from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


class CreditCardRecognizer(Recognizer):
    name = "credit_card_luhn"
    supported_types = frozenset({PIIType.CREDIT_CARD})

    def detect(self, text: str) -> list[PIIEntity]:
        raise NotImplementedError("Credit-card detection is scheduled for Phase 2")
