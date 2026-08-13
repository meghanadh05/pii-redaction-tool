"""Streamlit interface for the production DOCX redaction pipeline.

Uploaded and generated documents live only in a request-scoped temporary
directory. Preview originals are masked by default and raw values are retained
only in Streamlit session memory for the explicit unsafe-preview toggle.
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, TypeGuard, cast
from zipfile import is_zipfile

import streamlit as st
from docx import Document

from src.detector import DetectionEngine
from src.docx_processor import StoryKind, iter_text_containers
from src.identity_linker import IdentityLinker
from src.local_nlp import LocalSpacyProvider
from src.models import PIIType
from src.pseudonymizer import DeterministicPseudonymizer, normalize_entity_text
from src.recognizers.base import Recognizer
from src.redaction import RedactionWriteError, redact_docx
from src.redaction_plan import ReplacementPlanner


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PREVIEW_ROWS = 100
PROJECT_ROOT = Path(__file__).resolve().parent
BLIND_RESULT_PATH = PROJECT_ROOT / "docs" / "blind_evaluation_15a74a6.json"

# Categorical chart hues, validated for chroma, surface contrast, and
# colour-vision-deficiency separation in both light and dark surfaces.
SERIES_PRECISION = "#2a78d6"
SERIES_RECALL = "#eb6834"

DETECTION_METHODS = {
    PIIType.PERSON: "local spaCy NER + role context",
    PIIType.EMAIL: "regex + syntax validation",
    PIIType.PHONE: "regex + contextual safeguards",
    PIIType.COMPANY: "local NER + legal/context rules",
    PIIType.ADDRESS: "structure + local context",
    PIIType.SSN: "regex + identifier exclusions",
    PIIType.CREDIT_CARD: "regex + Luhn validation",
    PIIType.DOB: "date parsing + birth context",
    PIIType.IP_ADDRESS: "regex + ipaddress validation",
}

APP_CSS = """
<style>
    .stApp { background: #f7f9fc; }
    .block-container { max-width: 1180px; padding-top: 2rem; }
    .hero {
        padding: 2.1rem 2.2rem;
        border: 1px solid #dbe5f0;
        border-radius: 22px;
        background: linear-gradient(135deg, #0b2039 0%, #123c55 58%, #126e73 100%);
        box-shadow: 0 16px 42px rgba(13, 43, 67, .14);
        color: white;
        margin-bottom: 1rem;
    }
    .hero h1 { color: white; margin: 0 0 .35rem; font-size: 2.55rem; }
    .hero p { color: #dcebf2; margin: 0; font-size: 1.08rem; }
    .capabilities { display: flex; flex-wrap: wrap; gap: .55rem; margin: 1rem 0 .2rem; }
    .capability {
        background: rgba(255,255,255,.11); border: 1px solid rgba(255,255,255,.22);
        border-radius: 999px; padding: .38rem .72rem; font-size: .83rem; color: #f6fbff;
    }
    .section-kicker { color: #087f78; font-weight: 750; letter-spacing: .08em;
        text-transform: uppercase; font-size: .75rem; margin-bottom: .2rem; }
    .feature-card {
        min-height: 205px; padding: 1.2rem; border: 1px solid #dce5ee;
        border-radius: 16px; background: white; box-shadow: 0 5px 18px rgba(22,49,75,.05);
    }
    .feature-card h3 { margin: .55rem 0; font-size: 1.06rem; color: #123c55; }
    .feature-card p { color: #536476; font-size: .9rem; line-height: 1.5; }
    .feature-icon { font-size: 1.45rem; }
    .mini-code { background: #edf5f7; color: #173b4c; border-radius: 9px;
        padding: .55rem .7rem; font-family: ui-monospace, monospace; font-size: .76rem; }
    .pipeline { display: flex; flex-wrap: wrap; align-items: center; gap: .38rem;
        margin: 1rem 0 1.35rem; }
    .pipeline-step { background: white; border: 1px solid #cedce7; color: #173b4c;
        border-radius: 9px; padding: .48rem .68rem; font-weight: 650; font-size: .82rem; }
    .pipeline-arrow { color: #0a7d78; font-weight: 800; }
    .privacy-note { border-left: 4px solid #087f78; background: #eaf7f5;
        border-radius: 6px; padding: .8rem 1rem; color: #244753; }
    .metric-label { color: #607285; font-size: .78rem; text-transform: uppercase;
        letter-spacing: .05em; }
    div[data-testid="stMetric"] { background: white; border: 1px solid #dce5ee;
        border-radius: 14px; padding: .8rem 1rem; }
    div[data-testid="stTabs"] button { font-weight: 650; }
</style>
"""


@dataclass(frozen=True, slots=True)
class PreviewRow:
    """One planned replacement; raw input is deliberately hidden from repr."""

    entity_type: PIIType
    original: str = field(repr=False)
    replacement: str
    confidence: float
    method: str
    evidence: str
    story: StoryKind
    repeated: bool

    def display(self, *, unsafe_show_original: bool) -> dict[str, object]:
        return {
            "Type": self.entity_type.value,
            "Original": (
                self.original
                if unsafe_show_original
                else mask_entity(self.entity_type, self.original)
            ),
            "Synthetic replacement": self.replacement,
            "Confidence": self.confidence,
            "Method": self.method,
            "Evidence": self.evidence,
            "Location": self.story.value.replace("_", " ").title(),
            "Repeated": "Yes" if self.repeated else "No",
        }


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    filename: str
    source_sha256: str
    report: dict[str, Any]
    preview: tuple[PreviewRow, ...] = field(repr=False)
    elapsed: float


@dataclass(frozen=True, slots=True)
class RedactionResult:
    filename: str
    content: bytes = field(repr=False)
    report: dict[str, Any]
    elapsed: float


def _is_analysis_result(value: object) -> TypeGuard[AnalysisResult]:
    """Accept session objects created by the app's immediately preceding rerun."""

    return all(
        hasattr(value, attribute)
        for attribute in ("filename", "source_sha256", "report", "preview", "elapsed")
    )


def _is_redaction_result(value: object) -> TypeGuard[RedactionResult]:
    """Accept a redaction result across Streamlit's module reruns."""

    return all(
        hasattr(value, attribute)
        for attribute in ("filename", "content", "report", "elapsed")
    )


def _masked_words(value: str) -> str:
    return re.sub(
        r"[A-Za-z0-9]+",
        lambda match: match.group()[0] + "•" * min(max(len(match.group()) - 1, 2), 7),
        value,
    )


def mask_entity(entity_type: PIIType, value: str) -> str:
    """Return a useful but privacy-conscious representation of an entity."""

    if entity_type is PIIType.EMAIL and "@" in value:
        local, domain = value.split("@", maxsplit=1)
        suffix = "." + domain.rsplit(".", maxsplit=1)[-1] if "." in domain else ""
        domain_name = domain[: -len(suffix)] if suffix else domain
        return f"{local[:2]}•••@{domain_name[:2]}•••{suffix}"
    if entity_type is PIIType.PHONE:
        prefix = "+" if value.strip().startswith("+") else ""
        return f"{prefix}••••••••{re.sub(r'\D', '', value)[-2:]}"
    if entity_type is PIIType.SSN:
        return f"•••-••-{re.sub(r'\D', '', value)[-2:]}"
    if entity_type is PIIType.CREDIT_CARD:
        return f"•••• •••• •••• {re.sub(r'\D', '', value)[-4:]}"
    if entity_type is PIIType.DOB:
        return "•• •••• ••••"
    if entity_type is PIIType.IP_ADDRESS:
        return "•••.•••.•••.•••" if "." in value else "••••:••••:…"
    return _masked_words(value)


def _signals(metadata: object) -> str:
    if not isinstance(metadata, (tuple, list)):
        return "context-qualified"
    values = [str(item).replace("_", " ").lower() for item in metadata]
    return ", ".join(values[:3]) or "context-qualified"


def local_language_model() -> LocalSpacyProvider:
    """Load a provider scoped to one operation so its text cache is not shared."""

    provider = LocalSpacyProvider()
    provider.entities("Warm up the local language pipeline.")
    return provider


def _recognizers() -> tuple[Recognizer, ...]:
    """Construct recognizers while sharing the cached local NER provider."""

    from src.recognizers import (  # Local import keeps app startup lightweight.
        AddressRecognizer,
        CreditCardRecognizer,
        DOBRecognizer,
        EmailRecognizer,
        IPAddressRecognizer,
        OrganizationRecognizer,
        PersonRecognizer,
        PhoneRecognizer,
        SSNRecognizer,
    )

    provider = local_language_model()
    return (
        EmailRecognizer(),
        PhoneRecognizer(),
        SSNRecognizer(),
        CreditCardRecognizer(),
        IPAddressRecognizer(),
        DOBRecognizer(),
        PersonRecognizer(provider),
        OrganizationRecognizer(provider),
        AddressRecognizer(provider),
    )


def analyze_upload(*, data: bytes, filename: str, secret: bytes) -> AnalysisResult:
    """Build the real replacement plan without mutating the uploaded DOCX."""

    workspace = Path(tempfile.mkdtemp(prefix="pii-redaction-analysis-"))
    try:
        source = workspace / "source.docx"
        source.write_bytes(data)
        if not is_zipfile(source):
            raise ValueError("That file is not a valid .docx (not a Word package).")

        started = time.monotonic()
        document = Document(str(source))
        containers = tuple(iter_text_containers(document))
        engine = DetectionEngine(_recognizers())
        plan = ReplacementPlanner(
            engine,
            DeterministicPseudonymizer(secret),
            identity_linker=IdentityLinker(secret),
        ).build(containers)

        occurrence_counts = Counter(
            (
                item.entity.entity_type,
                normalize_entity_text(item.entity.entity_type, item.entity.text),
            )
            for item in plan.replacements
        )
        preview = tuple(
            PreviewRow(
                entity_type=item.entity.entity_type,
                original=item.entity.text,
                replacement=item.replacement,
                confidence=item.entity.confidence,
                method=DETECTION_METHODS[item.entity.entity_type],
                evidence=_signals(item.entity.metadata.get("signals")),
                story=item.story_type,
                repeated=(
                    occurrence_counts[
                        (
                            item.entity.entity_type,
                            normalize_entity_text(
                                item.entity.entity_type, item.entity.text
                            ),
                        )
                    ]
                    > 1
                ),
            )
            for item in plan.replacements
        )
        report = plan.summary()
        report.update(
            {
                "source_name": Path(filename).name,
                "source_size_bytes": len(data),
                "section_count": len(document.sections),
                "top_level_table_count": len(document.tables),
                "run_count": sum(
                    len(container.runs)
                    + sum(len(mirror.runs) for mirror in container.mirrors)
                    for container in containers
                ),
            }
        )
        return AnalysisResult(
            filename=Path(filename).name,
            source_sha256=sha256(data).hexdigest(),
            report=report,
            preview=preview,
            elapsed=time.monotonic() - started,
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def redact_upload(*, data: bytes, filename: str, secret: bytes) -> RedactionResult:
    """Redact uploaded bytes and return the result without leaving files behind."""

    workspace = Path(tempfile.mkdtemp(prefix="pii-redaction-write-"))
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
            secret=secret,
            key_source="ephemeral_per_upload",
        )
        return RedactionResult(
            filename=f"{Path(filename).stem}_redacted.docx",
            content=output.read_bytes(),
            report=report,
            elapsed=time.monotonic() - started,
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def _render_hero() -> None:
    st.markdown(
        """
        <div class="hero">
          <div class="section-kicker" style="color:#8fe3dc">Privacy engineering demo</div>
          <h1>PII Redaction Tool</h1>
          <p>Hybrid DOCX PII Detection &amp; Deterministic Pseudonymization</p>
          <div class="capabilities">
            <span class="capability">9 PII types</span>
            <span class="capability">Run-aware DOCX</span>
            <span class="capability">Local NLP</span>
            <span class="capability">Deterministic replacements</span>
            <span class="capability">Residual leak scan</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_pipeline() -> None:
    steps = (
        "Upload",
        "Document structure",
        "PII detection",
        "Confidence + method",
        "Pseudonymization",
        "DOCX rewrite",
        "Leak scan",
        "Download",
    )
    content = '<div class="pipeline">'
    for index, step in enumerate(steps):
        if index:
            content += '<span class="pipeline-arrow">→</span>'
        content += f'<span class="pipeline-step">{step}</span>'
    st.markdown(content + "</div>", unsafe_allow_html=True)


def _render_feature_cards() -> None:
    columns = st.columns(4)
    cards = (
        (
            "🧩",
            "Run-aware DOCX",
            "Detects PII even when Word fragments a value across formatting runs.",
            'Run 1: "Anaya "<br>Run 2: "Varman"<br>↓ &nbsp; Anaya Varman',
        ),
        (
            "🧠",
            "Hybrid detection",
            "Validators handle structured PII; local spaCy and contextual rules handle semantic PII.",
            "regex + validation<br>NER + local evidence",
        ),
        (
            "🔁",
            "Deterministic synthesis",
            "The same normalized source entity always receives the same synthetic value within a run.",
            "Devika Senvar → Aarav Iyer<br>Devika Senvar → Aarav Iyer",
        ),
        (
            "✅",
            "Post-redaction verification",
            "Reopens the output, validates DOCX structure, and re-scans supported text for residual PII.",
            "rewrite → reopen → scan",
        ),
    )
    for column, (icon, title, body, example) in zip(columns, cards, strict=True):
        with column:
            st.markdown(
                f"""
                <div class="feature-card">
                  <div class="feature-icon">{icon}</div>
                  <h3>{title}</h3><p>{body}</p>
                  <div class="mini-code">{example}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_analysis(result: AnalysisResult) -> None:
    report = result.report
    by_type = report["planned_replacements_by_type"]
    confidences: dict[PIIType, list[float]] = defaultdict(list)
    for row in result.preview:
        confidences[row.entity_type].append(row.confidence)

    st.subheader("Detection dashboard")
    st.caption(
        f"Analyzed {result.filename} locally in {result.elapsed:.1f}s. "
        "No document text appears in application logs."
    )
    leading_types = sorted(
        PIIType,
        key=lambda item: int(by_type.get(item.value, 0)),
        reverse=True,
    )[:5]
    for column, entity_type in zip(st.columns(5), leading_types, strict=True):
        column.metric(
            entity_type.value.replace("_", " ").title(),
            int(by_type.get(entity_type.value, 0)),
        )

    rows = []
    for entity_type in PIIType:
        values = confidences[entity_type]
        rows.append(
            {
                "PII type": entity_type.value,
                "Count": int(by_type.get(entity_type.value, 0)),
                "Detection method": DETECTION_METHODS[entity_type],
                "Average confidence": (
                    round(sum(values) / len(values), 3) if values else None
                ),
            }
        )
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        column_config={
            "Average confidence": st.column_config.NumberColumn(format="%.3f")
        },
    )

    st.subheader("Document structure")
    structure = st.columns(5)
    structure[0].metric("Containers", report["container_count"])
    structure[1].metric("Sections", report["section_count"])
    structure[2].metric("Tables", report["top_level_table_count"])
    structure[3].metric("Word runs", report["run_count"])
    structure[4].metric("Cross-run spans", report["cross_run_replacement_count"])
    if report["conflict_count"]:
        st.error(
            f"Analysis found {report['conflict_count']} structural conflict(s). "
            "Redaction is disabled to avoid corrupting the document."
        )
    else:
        st.success("Replacement plan is conflict-free and ready for preview.")


def _render_preview(result: AnalysisResult) -> None:
    st.subheader("Privacy-safe replacement preview")
    st.write(
        "Review the conflict-resolved plan before the DOCX is changed. Originals "
        "are masked by default; synthetic replacements are safe to display."
    )
    available_types = [
        entity_type.value
        for entity_type in PIIType
        if any(row.entity_type is entity_type for row in result.preview)
    ]
    selected_types = st.multiselect(
        "PII types",
        available_types,
        default=available_types,
        key="preview_types",
    )
    unsafe = st.toggle(
        "Show original PII (unsafe)",
        value=False,
        help=(
            "Reveals source values only in this browser session. Values are not "
            "written to reports or application logs."
        ),
    )
    if unsafe:
        st.warning(
            "Unsafe preview is enabled. Do not share screenshots or use this mode "
            "on a public display."
        )
    filtered = [
        row for row in result.preview if row.entity_type.value in selected_types
    ]
    st.dataframe(
        [
            row.display(unsafe_show_original=unsafe)
            for row in filtered[:MAX_PREVIEW_ROWS]
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "Confidence": st.column_config.ProgressColumn(
                min_value=0.0, max_value=1.0, format="%.2f"
            )
        },
    )
    if len(filtered) > MAX_PREVIEW_ROWS:
        st.caption(
            f"Showing the first {MAX_PREVIEW_ROWS} of {len(filtered)} selected "
            "replacements to keep the browser responsive. All are applied."
        )


def _render_verification(result: RedactionResult) -> None:
    report = result.report
    verification = report.get("post_save_verification", {})
    residual = report.get("residual_supported_text_scan", {})
    package = report.get("package_validation", {})
    structure_ok = all(
        bool(verification.get(key))
        for key in (
            "reopened_successfully",
            "container_id_set_preserved",
            "all_affected_container_text_verified",
            "run_count_preserved",
        )
    )

    st.subheader("Redaction and verification")
    columns = st.columns(5)
    columns[0].metric("Replacements", report.get("applied_replacement_count", 0))
    columns[1].metric("Cross-run", report.get("cross_run_replacement_count", 0))
    columns[2].metric("Conflicts", report.get("conflict_count", 0))
    columns[3].metric("Residual review", residual.get("review_required_count", 0))
    columns[4].metric("Processing time", f"{result.elapsed:.1f}s")

    left, right = st.columns(2)
    with left:
        if structure_ok and package.get("zip_integrity_valid"):
            st.success("DOCX integrity passed after save and reopen.")
        else:
            st.error("DOCX integrity or structural verification did not pass.")
        if report.get("conflict_count", 0) == 0:
            st.success("No structural replacement conflicts.")
        else:
            st.error("Structural conflicts were reported.")
    with right:
        unclassified = int(residual.get("unclassified_residual_count", 0))
        broad = int(residual.get("broad_overlap_review_count", 0))
        if unclassified == 0 and broad == 0:
            st.success("Residual scan found no review-required supported text.")
        else:
            st.warning(
                f"Residual scan flagged {unclassified} unclassified and {broad} "
                "broad-overlap span(s) for contextual review."
            )
        st.info(
            f"{residual.get('known_synthetic_detection_count', 0)} residual "
            "detections are recognized synthetic replacements, which is expected."
        )

    st.download_button(
        "Download redacted DOCX",
        data=result.content,
        file_name=result.filename,
        mime=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        type="primary",
        width="stretch",
    )
    with st.expander("Privacy-safe verification report"):
        st.caption("Counts and validation results only; raw detections are omitted.")
        st.json(report)


def load_blind_evaluation() -> dict[str, Any] | None:
    """Load the immutable, scored-once evaluation artifact shipped with the app.

    Returns ``None`` when the artifact is absent so a deployment that omits it
    degrades to a message rather than crashing the tab.
    """

    try:
        return cast(
            dict[str, Any],
            json.loads(BLIND_RESULT_PATH.read_text(encoding="utf-8")),
        )
    except (OSError, ValueError):
        return None


def _render_evaluation() -> None:
    result = load_blind_evaluation()
    if result is None:
        st.warning(
            "The evaluation artifact was not packaged with this deployment. "
            "Measured metrics are in the evaluation report linked below."
        )
        st.markdown(
            "[Read the full evaluation report]"
            "(https://github.com/meghanadh05/pii-redaction-tool/blob/main/"
            "docs/evaluation_report.md)"
        )
        return
    exact = result["metrics"]["exact"]
    micro = exact["micro"]
    st.subheader("Measured model performance")
    st.write(
        "Primary metrics come from the frozen 180-container set labelled after "
        "the recognizers were frozen and scored once. The sample is risk-stratified, "
        "and the report discloses annotator and boundary-convention limitations."
    )
    values = (
        ("Precision", micro["precision"]),
        ("Recall", micro["recall"]),
        ("F1", micro["f1"]),
        ("Entity-set accuracy", micro["entity_detection_accuracy"]),
    )
    for column, (label, value) in zip(st.columns(4), values, strict=True):
        column.metric(label, f"{value * 100:.1f}%")

    st.caption(
        "Accuracy = TP / (TP + FP + FN). Token accuracy is not used because the "
        "large non-PII majority would obscure entity and boundary errors."
    )
    per_type = exact["by_type"]
    positive_types = (
        PIIType.PERSON,
        PIIType.COMPANY,
        PIIType.ADDRESS,
        PIIType.EMAIL,
        PIIType.PHONE,
    )
    chart_rows = [
        {
            "PII type": entity_type.value,
            "Precision": per_type[entity_type.value]["precision"],
            "Recall": per_type[entity_type.value]["recall"],
        }
        for entity_type in positive_types
    ]
    st.bar_chart(
        chart_rows,
        x="PII type",
        y=["Precision", "Recall"],
        horizontal=True,
        # Validated categorical slots 1 and 2: both clear the chroma floor,
        # 3:1 surface contrast, and colour-vision-deficiency separation.
        color=[SERIES_PRECISION, SERIES_RECALL],
    )
    relaxed = result["metrics"]["address_relaxed"]
    st.caption(
        "ADDRESS exact precision/recall is 57.1% / 64.0%; relaxed one-to-one "
        f"overlap is {relaxed['precision'] * 100:.1f}% / "
        f"{relaxed['recall'] * 100:.1f}%, showing that many errors are boundaries."
    )

    st.subheader("Generalization gap")
    st.dataframe(
        [
            {
                "Evaluation": "Blind, scored once (primary)",
                "Precision": 0.675,
                "Recall": 0.839,
                "F1": 0.748,
                "Accuracy": 0.597,
            },
            {
                "Evaluation": "Post-fix reused set (diagnostic only)",
                "Precision": 0.843,
                "Recall": 0.901,
                "F1": 0.871,
                "Accuracy": 0.771,
            },
        ],
        hide_index=True,
        width="stretch",
        column_config={
            item: st.column_config.NumberColumn(format="%.3f")
            for item in ("Precision", "Recall", "F1", "Accuracy")
        },
    )
    st.warning(
        "PERSON is the main risk: blind precision is 19.1%. Title-Cased legal "
        "defined terms often resemble names, causing over-redaction rather than "
        "confirmed leakage. This blind set was not used for further tuning."
    )
    st.markdown(
        "[Read the full evaluation report]"
        "(https://github.com/meghanadh05/pii-redaction-tool/blob/main/"
        "docs/evaluation_report.md)"
    )


def _render_upload_and_analyze() -> Any:
    """Render the single upload control shared by every tab.

    It sits above the tab bar so the primary action is visible from the
    Overview page onwards, and so only one uploader owns the file state. The
    accepted upload is returned so later stages can re-read the source bytes
    without retaining the document in session state.
    """

    upload = st.file_uploader(
        "Upload a DOCX document",
        type=["docx"],
        accept_multiple_files=False,
        help="The document to scan for PII. Nothing is stored after processing.",
    )
    if upload is None:
        st.caption(
            f"Maximum {MAX_UPLOAD_BYTES // 1_048_576} MB. Use synthetic or test "
            "data — this is a public demo."
        )
        return None

    if upload.size > MAX_UPLOAD_BYTES:
        st.error(
            f"That file is {upload.size / 1_048_576:.1f} MB. This demo accepts up "
            f"to {MAX_UPLOAD_BYTES // 1_048_576} MB — run the CLI locally for "
            "larger documents."
        )
        return None

    source_data = upload.getvalue()
    _reset_for_new_upload(sha256(source_data).hexdigest())
    st.success(f"Loaded: {upload.name} ({upload.size / 1_048_576:.2f} MB)")

    if st.button("Analyze document", type="primary"):
        secret = secrets.token_bytes(32)
        try:
            with st.spinner("Reconstructing DOCX text and running local detectors…"):
                analyzed = analyze_upload(
                    data=source_data,
                    filename=upload.name,
                    secret=secret,
                )
            st.session_state["analysis"] = analyzed
            st.session_state["analysis_secret"] = secret
            st.session_state.pop("redaction", None)
        except (OSError, ValueError) as error:
            st.error(f"Could not analyze that document: {error}")

    if _is_analysis_result(st.session_state.get("analysis")):
        st.caption("Analysis complete — see the **Analyze** tab for detections.")
    return upload


def _reset_for_new_upload(source_sha256: str) -> None:
    if st.session_state.get("active_source_sha256") == source_sha256:
        return
    for key in ("analysis", "analysis_secret", "redaction", "preview_types"):
        st.session_state.pop(key, None)
    st.session_state["active_source_sha256"] = source_sha256


def main() -> None:
    st.set_page_config(
        page_title="PII Redaction Tool",
        page_icon="🛡️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(APP_CSS, unsafe_allow_html=True)
    _render_hero()
    upload = _render_upload_and_analyze()
    st.divider()

    with st.sidebar:
        st.header("Privacy boundary")
        st.warning(
            "This public demo processes uploads on its hosting server. Use synthetic "
            "or test data—not live personal information."
        )
        st.write(
            "Detection is in-process with a packaged spaCy model. No document "
            "content is sent to an external AI or PII API. Temporary files are "
            "deleted immediately after each operation."
        )
        st.divider()
        st.markdown("[Source code](https://github.com/meghanadh05/pii-redaction-tool)")
        st.caption("English/Indian corporate documents are the strongest domain.")

    overview_tab, analyze_tab, redact_tab, verify_tab, evaluation_tab = st.tabs(
        ["Overview", "Analyze", "Redact", "Verify", "Evaluation"]
    )

    with overview_tab:
        st.markdown(
            '<div class="section-kicker">End-to-end workflow</div>',
            unsafe_allow_html=True,
        )
        st.header("More than find-and-replace")
        _render_pipeline()
        _render_feature_cards()
        st.markdown("&nbsp;", unsafe_allow_html=True)
        st.markdown(
            '<div class="privacy-note"><strong>Local NLP:</strong> the recognizer '
            "runs inside this application process. Reports contain counts, methods, "
            "confidence, and verification status—not raw detected values.</div>",
            unsafe_allow_html=True,
        )

    with analyze_tab:
        st.subheader("Detection results")
        current_analysis = st.session_state.get("analysis")
        if _is_analysis_result(current_analysis):
            _render_analysis(current_analysis)
        else:
            st.info(
                "Upload a `.docx` above and select **Analyze document** to build a "
                "conflict-resolved detection plan. Analysis alone never alters or "
                "saves a document."
            )

    with redact_tab:
        current_analysis = st.session_state.get("analysis")
        if not _is_analysis_result(current_analysis):
            st.info("Analyze a DOCX first to review its replacement plan.")
        elif upload is None:
            st.info("Re-select the analyzed DOCX to continue.")
        else:
            _render_preview(current_analysis)
            conflict_count = int(current_analysis.report.get("conflict_count", 0))
            if st.button(
                "Redact and verify DOCX",
                type="primary",
                disabled=conflict_count > 0,
                width="stretch",
            ):
                session_secret = st.session_state.get("analysis_secret")
                if not isinstance(session_secret, bytes):
                    st.error("The session key expired. Analyze the document again.")
                else:
                    try:
                        with st.spinner(
                            "Applying replacements, reopening the DOCX, and scanning "
                            "for residual PII…"
                        ):
                            st.session_state["redaction"] = redact_upload(
                                data=upload.getvalue(),
                                filename=upload.name,
                                secret=session_secret,
                            )
                        st.success("Redacted document is ready in the Verify tab.")
                    except RedactionWriteError as error:
                        st.error(
                            f"Redaction stopped before output was written: {error}"
                        )
                    except (OSError, ValueError) as error:
                        st.error(f"Could not process that document: {error}")

    with verify_tab:
        result = st.session_state.get("redaction")
        if _is_redaction_result(result):
            _render_verification(result)
        else:
            st.info("Redact a document to see integrity and residual-scan results.")

    with evaluation_tab:
        _render_evaluation()


if __name__ == "__main__":
    main()
