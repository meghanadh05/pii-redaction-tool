"""Streamlit web demo: upload a DOCX, download a redacted copy.

The demo wraps :func:`src.redaction.redact_docx` without changing detection or
replacement behaviour. Each request uses its own ephemeral pseudonymization key,
and the uploaded and redacted documents are held in a temporary directory that
is deleted as soon as the result has been read into memory.
"""

from __future__ import annotations

import secrets
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, NamedTuple
from zipfile import is_zipfile

import streamlit as st

from src.local_nlp import LocalSpacyProvider
from src.models import PIIType
from src.redaction import RedactionWriteError, redact_docx


MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class RedactionResult(NamedTuple):
    filename: str
    content: bytes
    report: dict[str, Any]
    elapsed: float


@st.cache_resource(show_spinner=False)
def warm_language_model() -> dict[str, str]:
    """Load the spaCy pipeline once per server process, not once per upload."""

    provider = LocalSpacyProvider()
    provider.entities("Warm up the pipeline.")
    return provider.model_versions()


def redact_upload(*, data: bytes, filename: str) -> RedactionResult:
    """Redact uploaded bytes and return the result without leaving files behind."""

    workspace = Path(tempfile.mkdtemp(prefix="pii-redaction-"))
    try:
        source = workspace / "source.docx"
        source.write_bytes(data)
        if not is_zipfile(source):
            raise ValueError("That file is not a valid .docx (not a Word package).")

        output = workspace / "redacted.docx"
        started = time.monotonic()
        report = redact_docx(
            source,
            output,
            secret=secrets.token_bytes(32),
            key_source="ephemeral_per_request",
        )
        return RedactionResult(
            filename=f"{Path(filename).stem}_redacted.docx",
            content=output.read_bytes(),
            report=report,
            elapsed=time.monotonic() - started,
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def render_summary(result: RedactionResult) -> None:
    report = result.report
    applied = int(report.get("applied_replacement_count", 0))
    cross_run = int(report.get("cross_run_replacement_count", 0))

    left, middle, right = st.columns(3)
    left.metric("Values replaced", applied)
    middle.metric("Spanning multiple Word runs", cross_run)
    right.metric("Time", f"{result.elapsed:.0f}s")

    by_type = report.get("planned_replacements_by_type", {})
    st.dataframe(
        [
            {
                "PII type": entity_type.value,
                "Replaced": by_type.get(entity_type.value, 0),
            }
            for entity_type in PIIType
        ],
        hide_index=True,
        use_container_width=True,
    )
    st.caption(
        "A zero count usually means the document contains none of that type. "
        "The supplied prospectus contained no SSNs, credit cards, dates of "
        "birth, or IP addresses."
    )

    verification = report.get("post_save_verification", {})
    structure_ok = all(
        bool(verification.get(key))
        for key in (
            "reopened_successfully",
            "container_id_set_preserved",
            "all_affected_container_text_verified",
            "run_count_preserved",
        )
    )
    review_required = int(
        report.get("residual_supported_text_scan", {}).get("review_required_count", 0)
    )
    conflicts = int(report.get("conflict_count", 0))

    st.subheader("Verification")
    if structure_ok:
        st.success(
            "Document structure preserved — the saved file was reopened and its "
            "containers and Word run count verified against the original."
        )
    else:
        st.warning("Structure verification incomplete — see the full report below.")
    if conflicts:
        st.warning(f"{conflicts} structural conflict(s) reported.")
    else:
        st.success("No structural conflicts.")
    if review_required:
        st.warning(
            f"{review_required} span(s) resemble PII but did not match a planned "
            "replacement. They are flagged for manual review."
        )
    else:
        st.success("No unclassified residual PII found in supported text.")

    with st.expander("Full verification report (JSON)"):
        st.caption(
            "Counts and validation results only — this report never contains "
            "detected values."
        )
        st.json(report)


def main() -> None:
    st.set_page_config(page_title="PII Redaction Tool", page_icon="🛡️")
    st.title("🛡️ PII Redaction Tool")
    st.write(
        "Upload a Word document. The tool detects full names, email addresses, "
        "phone numbers, company names, physical addresses, SSNs, credit card "
        "numbers, dates of birth, and IP addresses, replaces each with a "
        "realistic fake value, and returns a `.docx` with its formatting, "
        "tables, headers, and text boxes intact."
    )

    with st.sidebar:
        st.header("Before you upload")
        st.warning(
            "This is a public demo. Your document is uploaded to the server "
            "running this app, redacted in a temporary directory, and deleted "
            "immediately afterwards. Please use test data rather than a "
            "document containing live personal data."
        )
        st.markdown(
            "Detection runs in-process with a local spaCy model. No document "
            "content is sent to any third-party API."
        )
        st.header("How it works")
        st.markdown(
            "Structured types (email, phone, SSN, credit card, IP, date of "
            "birth) use regular expressions plus validators — Luhn, "
            "`ipaddress`, and a required birth-date context. Names, companies, "
            "and addresses combine a local spaCy model with document-specific "
            "context and boundary rules.\n\n"
            "Replacements are deterministic within a run, so a repeated name "
            "maps to the same fake name throughout the document. Each request "
            "uses a fresh key, so results are not linkable across uploads."
        )
        st.markdown(
            "[Source and evaluation report]"
            "(https://github.com/meghanadh05/pii-redaction-tool)"
        )
        st.caption(
            "PERSON precision is the weakest measured category — expect some "
            "over-redaction of capitalized prose."
        )

    upload = st.file_uploader(
        "Word document (.docx, up to 10 MB)",
        type=["docx"],
        accept_multiple_files=False,
    )

    if upload is not None and upload.size > MAX_UPLOAD_BYTES:
        st.error(
            f"That file is {upload.size / 1_048_576:.1f} MB. This demo accepts "
            f"up to {MAX_UPLOAD_BYTES // 1_048_576} MB — run the CLI locally "
            "for larger documents."
        )
        return

    if st.button("Redact document", type="primary", disabled=upload is None):
        warm_language_model()
        try:
            with st.spinner("Detecting PII and rewriting the document…"):
                st.session_state["result"] = redact_upload(
                    data=upload.getvalue(),  # type: ignore[union-attr]
                    filename=upload.name,  # type: ignore[union-attr]
                )
        except RedactionWriteError as error:
            st.session_state.pop("result", None)
            st.error(f"Redaction stopped before writing anything: {error}")
        except (OSError, ValueError) as error:
            st.session_state.pop("result", None)
            st.error(f"Could not process that document: {error}")

    result = st.session_state.get("result")
    if isinstance(result, RedactionResult):
        st.download_button(
            "⬇️ Download redacted document",
            data=result.content,
            file_name=result.filename,
            mime=(
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
            type="primary",
        )
        render_summary(result)


if __name__ == "__main__":
    main()
