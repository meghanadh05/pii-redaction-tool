"""Read-only full-document redaction planning and dry-run reporting."""

from __future__ import annotations

import os
import secrets
from hashlib import sha256
from pathlib import Path

from docx import Document

from src.detector import DetectionEngine
from src.docx_processor import EXTRACTOR_SCHEMA_VERSION, iter_text_containers
from src.identity_linker import IdentityLinker
from src.pseudonymizer import DeterministicPseudonymizer
from src.recognizers import all_recognizers
from src.redaction_plan import ReplacementPlanner


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_dry_run_report(
    input_path: Path | str,
    *,
    secret: bytes | None = None,
    key_source: str = "ephemeral_dry_run",
) -> dict[str, object]:
    """Build a complete plan without mutating or saving the source document."""

    source = Path(input_path)
    if not source.is_file():
        raise FileNotFoundError(f"Input DOCX does not exist: {source}")
    before_hash = _file_sha256(source)
    effective_secret = secret or secrets.token_bytes(32)
    document = Document(str(source))
    containers = tuple(iter_text_containers(document))
    planner = ReplacementPlanner(
        DetectionEngine(all_recognizers()),
        DeterministicPseudonymizer(effective_secret),
        identity_linker=IdentityLinker(effective_secret),
    )
    plan = planner.build(containers)
    after_hash = _file_sha256(source)
    return {
        "report_schema_version": "1.0",
        "source_name": source.name,
        "source_sha256": before_hash,
        "source_unchanged": before_hash == after_hash,
        "extractor_schema_version": EXTRACTOR_SCHEMA_VERSION,
        "pseudonym_key_source": key_source,
        **plan.summary(),
    }


def secret_from_environment(variable_name: str) -> tuple[bytes | None, str]:
    value = os.environ.get(variable_name)
    if value is None:
        return None, "ephemeral_dry_run"
    secret = value.encode()
    if len(secret) < 16:
        raise ValueError(f"{variable_name} must contain at least 16 UTF-8 bytes")
    return secret, f"environment:{variable_name}"
