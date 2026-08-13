"""Keyed deterministic, type-specific synthetic replacement generation."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

from src.models import PIIEntity, PIIType
from src.recognizers.credit_card import CreditCardRecognizer
from src.recognizers.dob import DOBRecognizer
from src.recognizers.email import EmailRecognizer
from src.recognizers.ip_address import IPAddressRecognizer
from src.recognizers.phone import PhoneRecognizer
from src.recognizers.ssn import SSNRecognizer


ReplacementFactory = Callable[[PIIEntity, int], str]


def normalize_entity_text(entity_type: PIIType, text: str) -> str:
    """Normalize equivalent appearances before deriving a pseudonym key."""

    text = text.strip()
    if entity_type in {PIIType.PHONE, PIIType.CREDIT_CARD, PIIType.SSN}:
        return re.sub(r"\D", "", text)
    if entity_type is PIIType.IP_ADDRESS:
        try:
            return ipaddress.ip_address(text).compressed
        except ValueError:
            return text.casefold()
    if entity_type is PIIType.DOB:
        return DOBRecognizer.normalize(text) or " ".join(text.casefold().split())
    if entity_type is PIIType.EMAIL:
        return text.casefold()
    return " ".join(text.casefold().split())


_FIRST_NAMES = (
    "Aarav",
    "Aditi",
    "Ananya",
    "Arjun",
    "Diya",
    "Ishaan",
    "Kavya",
    "Meera",
    "Neel",
    "Nisha",
    "Priya",
    "Rohan",
    "Saanvi",
    "Tara",
    "Vihaan",
    "Zoya",
)
_LAST_NAMES = (
    "Bose",
    "Desai",
    "Iyer",
    "Kapoor",
    "Kulkarni",
    "Mehta",
    "Menon",
    "Nair",
    "Patel",
    "Rao",
    "Sen",
    "Shah",
    "Sharma",
    "Singh",
    "Verma",
    "Yadav",
)
_COMPANY_WORDS = (
    "Arcadia",
    "Bluehaven",
    "Cedar",
    "Evergreen",
    "Harbor",
    "Meridian",
    "Northstar",
    "Silverline",
)
_COMPANY_INDUSTRIES = (
    "Advisory",
    "Industries",
    "Logistics",
    "Manufacturing",
    "Securities",
    "Services",
    "Technologies",
    "Ventures",
)


def _synthetic_person(seed: int) -> str:
    first = _FIRST_NAMES[seed % len(_FIRST_NAMES)]
    last = _LAST_NAMES[(seed >> 8) % len(_LAST_NAMES)]
    middle = chr(ord("A") + ((seed >> 16) % 26))
    return f"{first} {middle}. {last}"


def _person_factory(entity: PIIEntity, seed: int) -> str:
    return _synthetic_person(seed)


def _email_factory(entity: PIIEntity, seed: int) -> str:
    identity_linked = entity.metadata.get("link_scope") == "identity"
    if identity_linked:
        tokens = [
            re.sub(r"[^a-z]", "", token.casefold())
            for token in _synthetic_person(seed).split()
        ]
        local = ".".join(token for token in (tokens[0], tokens[-1]) if token)
    else:
        local = f"synthetic.contact+{seed & 0xFFFFFF:06x}"
    return f"{local}@example.com"


def _phone_factory(entity: PIIEntity, seed: int) -> str:
    # NANPA reserves 202-555-0100 through 0199 for fictional use.
    return f"+1 202-555-{100 + seed % 100:04d}"


def _company_factory(entity: PIIEntity, seed: int) -> str:
    name = _COMPANY_WORDS[seed % len(_COMPANY_WORDS)]
    industry = _COMPANY_INDUSTRIES[(seed >> 8) % len(_COMPANY_INDUSTRIES)]
    token = f"{(seed >> 16) & 0xFFFF:04X}"
    return f"Example {name} {industry} {token} Private Limited"


def _address_factory(entity: PIIEntity, seed: int) -> str:
    unit = 100 + seed % 900
    building = 1 + (seed >> 10) % 20
    postal = 411900 + (seed >> 16) % 100
    return (
        f"Unit {unit}, Example Heights {building}, Synthetic Avenue, "
        f"Pune – {postal:06d}, Maharashtra, India"
    )


def _ssn_factory(entity: PIIEntity, seed: int) -> str:
    area = 700 + seed % 199
    group = 1 + (seed >> 8) % 99
    serial = 1 + (seed >> 16) % 9999
    return f"{area:03d}-{group:02d}-{serial:04d}"


def _luhn_check_digit(prefix: str) -> str:
    for digit in "0123456789":
        candidate = prefix + digit
        if CreditCardRecognizer.passes_luhn(candidate):
            return digit
    raise RuntimeError("Unable to calculate Luhn check digit")


def _credit_card_factory(entity: PIIEntity, seed: int) -> str:
    # 424242 is a conventional test prefix; the suffix and checksum are keyed.
    prefix = "424242" + f"{seed % 1_000_000_000:09d}"
    digits = prefix + _luhn_check_digit(prefix)
    return " ".join(digits[index : index + 4] for index in range(0, 16, 4))


def _dob_factory(entity: PIIEntity, seed: int) -> str:
    synthetic = date(1970, 1, 1) + timedelta(days=seed % (30 * 365))
    original = entity.text
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", original):
        return synthetic.strftime("%Y-%m-%d")
    if "/" in original:
        return synthetic.strftime("%d/%m/%Y")
    if re.fullmatch(r"\d{1,2}-\d{1,2}-\d{4}", original):
        return synthetic.strftime("%d-%m-%Y")
    if re.match(r"[A-Za-z]", original):
        return synthetic.strftime("%B %d, %Y")
    return synthetic.strftime("%d %B %Y")


def _ip_factory(entity: PIIEntity, seed: int) -> str:
    try:
        version: int = ipaddress.ip_address(entity.text).version
    except ValueError:
        raw_version = entity.metadata.get("version", 4)
        version = raw_version if isinstance(raw_version, int) else 4
    if version == 6:
        return str(
            ipaddress.IPv6Address(
                int(ipaddress.IPv6Address("2001:db8::")) + 1 + seed % 65534
            )
        )
    return str(
        ipaddress.IPv4Address(int(ipaddress.IPv4Address("192.0.2.0")) + 1 + seed % 254)
    )


_TYPE_FACTORIES: dict[PIIType, ReplacementFactory] = {
    PIIType.PERSON: _person_factory,
    PIIType.EMAIL: _email_factory,
    PIIType.PHONE: _phone_factory,
    PIIType.COMPANY: _company_factory,
    PIIType.ADDRESS: _address_factory,
    PIIType.SSN: _ssn_factory,
    PIIType.CREDIT_CARD: _credit_card_factory,
    PIIType.DOB: _dob_factory,
    PIIType.IP_ADDRESS: _ip_factory,
}


def replacement_passes_validator(entity_type: PIIType, replacement: str) -> bool:
    """Validate synthetic structured values using production validators."""

    if entity_type is PIIType.EMAIL:
        results = EmailRecognizer().detect(replacement)
    elif entity_type is PIIType.PHONE:
        results = PhoneRecognizer().detect(replacement)
    elif entity_type is PIIType.SSN:
        results = SSNRecognizer().detect(replacement)
    elif entity_type is PIIType.CREDIT_CARD:
        results = CreditCardRecognizer().detect(replacement)
    elif entity_type is PIIType.DOB:
        return DOBRecognizer.normalize(replacement) is not None
    elif entity_type is PIIType.IP_ADDRESS:
        results = IPAddressRecognizer().detect(replacement)
    else:
        return bool(replacement.strip())
    return any(item.start == 0 and item.end == len(replacement) for item in results)


@dataclass(slots=True)
class DeterministicPseudonymizer:
    """Cache keyed replacements without storing raw source-to-fake mappings."""

    secret: bytes = field(repr=False)
    _replacement_cache: dict[str, str] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if len(self.secret) < 16:
            raise ValueError("Pseudonymization secret must contain at least 16 bytes")

    def _digest(self, entity: PIIEntity) -> bytes:
        identity_key = entity.metadata.get("identity_key")
        scope = str(entity.metadata.get("link_scope", entity.entity_type.value))
        if identity_key is None:
            normalized = normalize_entity_text(entity.entity_type, entity.text)
        else:
            normalized = " ".join(str(identity_key).casefold().split())
        material = f"{scope}\0{normalized}".encode()
        return hmac.new(self.secret, material, hashlib.sha256).digest()

    def stable_seed(self, entity: PIIEntity) -> int:
        return int.from_bytes(self._digest(entity)[:8], byteorder="big", signed=False)

    def replacement_for(
        self,
        entity: PIIEntity,
        factory: ReplacementFactory,
    ) -> str:
        digest = self._digest(entity).hex()
        cache_key = f"{entity.entity_type.value}:{digest}"
        if cache_key not in self._replacement_cache:
            original = normalize_entity_text(entity.entity_type, entity.text)
            base_seed = self.stable_seed(entity)
            for attempt in range(64):
                seed = (base_seed + attempt * 0x9E3779B97F4A7C15) & ((1 << 64) - 1)
                replacement = factory(entity, seed)
                if not replacement:
                    continue
                if normalize_entity_text(entity.entity_type, replacement) == original:
                    continue
                if not replacement_passes_validator(entity.entity_type, replacement):
                    continue
                self._replacement_cache[cache_key] = replacement
                break
            else:
                raise ValueError("Factory did not produce a distinct valid replacement")
        return self._replacement_cache[cache_key]

    def replacement_for_entity(self, entity: PIIEntity) -> str:
        return self.replacement_for(entity, _TYPE_FACTORIES[entity.entity_type])
