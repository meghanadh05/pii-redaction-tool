"""Credit-card candidate recognition with mandatory Luhn validation."""

from __future__ import annotations

import re

from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


class CreditCardRecognizer(Recognizer):
    name = "credit_card_luhn"
    supported_types = frozenset({PIIType.CREDIT_CARD})
    default_confidence = 0.99

    _pattern = re.compile(r"(?<!\d)(?P<card>(?:\d[ -]?){12,18}\d)(?!\d)")
    _identifier_context = re.compile(
        r"(?i)\b(?:CIN|DIN|ISIN|SEBI|registration|reference|folio|application|"
        r"account)\b[^\n]{0,24}$"
    )

    @staticmethod
    def normalize(value: str) -> str:
        return re.sub(r"\D", "", value)

    @staticmethod
    def passes_luhn(digits: str) -> bool:
        total = 0
        parity = len(digits) % 2
        for index, character in enumerate(digits):
            digit = int(character)
            if index % 2 == parity:
                digit *= 2
                if digit > 9:
                    digit -= 9
            total += digit
        return total % 10 == 0

    def detect(self, text: str) -> list[PIIEntity]:
        entities: list[PIIEntity] = []
        for match in self._pattern.finditer(text):
            value = match.group("card")
            digits = self.normalize(value)
            context = text[max(0, match.start() - 50) : match.start()]
            if (
                not 13 <= len(digits) <= 19
                or not self.passes_luhn(digits)
                or self._identifier_context.search(context)
            ):
                continue
            entities.append(
                PIIEntity(
                    entity_type=PIIType.CREDIT_CARD,
                    text=value,
                    start=match.start("card"),
                    end=match.end("card"),
                    confidence=self.default_confidence,
                    recognizer=self.name,
                    metadata={
                        "normalized": digits,
                        "validated": True,
                        "signals": ("CARD_CANDIDATE", "LUHN_VALID"),
                    },
                )
            )
        return entities
