"""IP recognizer scaffold: regex candidates plus ``ipaddress`` in Phase 2."""

from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


class IPAddressRecognizer(Recognizer):
    name = "ipaddress_validated"
    supported_types = frozenset({PIIType.IP_ADDRESS})

    def detect(self, text: str) -> list[PIIEntity]:
        raise NotImplementedError("IP detection is scheduled for Phase 2")
