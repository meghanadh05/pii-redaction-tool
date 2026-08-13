"""IPv4 and IPv6 recognition finalized by the standard ``ipaddress`` module."""

from __future__ import annotations

import ipaddress
import re

from src.models import PIIEntity, PIIType
from src.recognizers.base import Recognizer


class IPAddressRecognizer(Recognizer):
    name = "ipaddress_validated"
    supported_types = frozenset({PIIType.IP_ADDRESS})
    default_confidence = 0.99

    _ipv4_pattern = re.compile(r"(?<![\w.])(?P<ip>(?:\d{1,3}\.){3}\d{1,3})(?![\w.])")
    _ipv6_pattern = re.compile(
        r"(?<![0-9A-Fa-f:.])"
        r"(?P<ip>(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4})"
        r"(?![0-9A-Fa-f:.])"
    )

    @staticmethod
    def normalize(value: str) -> str:
        return ipaddress.ip_address(value).compressed

    def _entity_from_match(self, match: re.Match[str]) -> PIIEntity | None:
        value = match.group("ip")
        try:
            parsed = ipaddress.ip_address(value)
        except ValueError:
            return None
        return PIIEntity(
            entity_type=PIIType.IP_ADDRESS,
            text=value,
            start=match.start("ip"),
            end=match.end("ip"),
            confidence=self.default_confidence,
            recognizer=self.name,
            metadata={
                "normalized": parsed.compressed,
                "version": parsed.version,
                "validated": True,
                "signals": (f"IPV{parsed.version}_CANDIDATE", "IPADDRESS_VALID"),
            },
        )

    def detect(self, text: str) -> list[PIIEntity]:
        entities = [
            entity
            for pattern in (self._ipv4_pattern, self._ipv6_pattern)
            for match in pattern.finditer(text)
            if (entity := self._entity_from_match(match)) is not None
        ]
        unique = {
            (entity.start, entity.end, entity.entity_type): entity
            for entity in entities
        }
        return sorted(unique.values(), key=lambda item: (item.start, item.end))
