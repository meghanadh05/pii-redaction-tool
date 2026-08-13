"""Privacy-safe audits for DOCX drawing and shape metadata."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

from lxml import etree  # type: ignore[import-untyped]

from src.detector import DetectionEngine
from src.models import PIIType
from src.recognizers import structured_recognizers


_AUDITED_ATTRIBUTES = frozenset({"alt", "descr", "title", "name"})
_DRAWING_METADATA_ELEMENTS = frozenset({"docPr", "cNvPr", "shape", "imagedata"})


@dataclass(frozen=True, slots=True)
class ShapeMetadataAudit:
    """Aggregate metadata findings that never retain raw attribute values."""

    source_sha256: str
    xml_parts_scanned: int
    parts_with_shape_metadata: int
    attributes_by_kind: dict[str, int]
    unique_value_count: int
    potential_pii_by_type: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "source_sha256": self.source_sha256,
            "privacy_safe": True,
            "xml_parts_scanned": self.xml_parts_scanned,
            "parts_with_shape_metadata": self.parts_with_shape_metadata,
            "attributes_by_kind": dict(sorted(self.attributes_by_kind.items())),
            "accessible_description_or_title_count": (
                self.attributes_by_kind.get("alt", 0)
                + self.attributes_by_kind.get("descr", 0)
                + self.attributes_by_kind.get("title", 0)
            ),
            "selection_pane_name_count": self.attributes_by_kind.get("name", 0),
            "unique_value_count": self.unique_value_count,
            "potential_pii_by_type": dict(sorted(self.potential_pii_by_type.items())),
            "automatically_rewritten": False,
            "review_policy": (
                "Descriptions/titles may be exposed to assistive technology and "
                "shape names may be visible in Word's Selection Pane. They are "
                "audited but not automatically rewritten in Phase 2B."
            ),
        }


def audit_shape_metadata(
    path: Path | str,
    *,
    detector: DetectionEngine | None = None,
) -> ShapeMetadataAudit:
    """Audit drawing names/descriptions without returning their raw values."""

    source_path = Path(path)
    digest = sha256(source_path.read_bytes()).hexdigest()
    engine = detector or DetectionEngine(structured_recognizers())
    attribute_counts: Counter[str] = Counter()
    pii_counts: Counter[str] = Counter()
    value_hashes: set[str] = set()
    xml_parts_scanned = 0
    parts_with_metadata = 0

    with ZipFile(source_path) as package:
        for part_name in sorted(package.namelist()):
            if not part_name.startswith("word/") or not part_name.endswith(".xml"):
                continue
            root = etree.fromstring(package.read(part_name))
            xml_parts_scanned += 1
            part_has_metadata = False
            for element in root.iter():
                element_name = element.tag.rsplit("}", maxsplit=1)[-1]
                if element_name not in _DRAWING_METADATA_ELEMENTS:
                    continue
                for qualified_name, raw_value in element.attrib.items():
                    attribute_name = qualified_name.rsplit("}", maxsplit=1)[-1]
                    value = raw_value.strip()
                    if attribute_name not in _AUDITED_ATTRIBUTES or not value:
                        continue
                    part_has_metadata = True
                    attribute_counts[attribute_name] += 1
                    value_hashes.add(sha256(value.encode("utf-8")).hexdigest())
                    for entity in engine.detect(value):
                        pii_counts[entity.entity_type.value] += 1
            parts_with_metadata += int(part_has_metadata)

    return ShapeMetadataAudit(
        source_sha256=digest,
        xml_parts_scanned=xml_parts_scanned,
        parts_with_shape_metadata=parts_with_metadata,
        attributes_by_kind=dict(attribute_counts),
        unique_value_count=len(value_hashes),
        potential_pii_by_type={
            entity_type.value: pii_counts.get(entity_type.value, 0)
            for entity_type in PIIType
        },
    )
