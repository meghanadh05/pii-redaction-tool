from __future__ import annotations

import json
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement

from src.docx_audit import audit_shape_metadata


def test_shape_metadata_audit_reports_counts_without_raw_values(tmp_path: Path) -> None:
    source = tmp_path / "shape-metadata.docx"
    raw_value = "Contact person@example.test"
    document = Document()
    paragraph = document.add_paragraph()
    shape_properties = OxmlElement("wp:docPr")
    shape_properties.set("name", "Synthetic shape")
    shape_properties.set("descr", raw_value)
    paragraph._p.append(shape_properties)
    document.save(str(source))

    report = audit_shape_metadata(source).to_dict()
    serialized = json.dumps(report)

    assert report["attributes_by_kind"] == {"descr": 1, "name": 1}
    assert report["potential_pii_by_type"]["EMAIL"] == 1  # type: ignore[index]
    assert report["automatically_rewritten"] is False
    assert raw_value not in serialized
