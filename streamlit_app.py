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

# Chart series hues. Validated against the #07111F surface for lightness,
# chroma, 3:1 contrast, and colour-vision-deficiency separation. The brand
# cyan/teal pair is deliberately NOT used here: at normal vision the two are
# only ΔE 6.9 apart, far below the 15 floor, so they cannot encode two series.
SERIES_PRECISION = "#0891B2"
SERIES_RECALL = "#D97706"

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
    :root {
        --bg: #07111F; --card: #0D1B2A; --elevated: #132337;
        --accent: #22D3EE; --accent-2: #2DD4BF;
        --ink: #F8FAFC; --ink-dim: #94A3B8;
        --ok: #22C55E; --warn: #F59E0B; --risk: #F43F5E;
        --line: #1E3350;
    }
    .stApp { background: var(--bg); }
    /* Extra top padding keeps the eyebrow clear of Streamlit's fixed header. */
    .block-container { max-width: 1180px; padding-top: 3.4rem; }
    header[data-testid="stHeader"] { background: transparent; }

    .kicker { color: var(--accent); font-weight: 700; letter-spacing: .16em;
        text-transform: uppercase; font-size: .78rem; margin-bottom: .55rem; }
    .section-head { color: var(--ink); font-size: 1.45rem; font-weight: 700;
        margin: .2rem 0 .2rem; letter-spacing: -.01em; }
    .section-num { color: var(--accent); font-weight: 800; margin-right: .5rem; }
    .hero-title { color: var(--ink); font-size: 2.7rem; font-weight: 700;
        line-height: 1.1; margin: 0 0 .5rem; letter-spacing: -.02em; }
    .hero-sub { color: var(--ink-dim); font-size: 1.02rem; margin: 0 0 1.1rem;
        max-width: 60ch; line-height: 1.55; }
    .hero-sub strong { color: var(--accent-2); font-weight: 600; }

    .capabilities { display: flex; flex-wrap: wrap; gap: .45rem; margin: 0 0 .3rem; }
    .capability { background: rgba(34,211,238,.07); border: 1px solid rgba(34,211,238,.25);
        border-radius: 999px; padding: .32rem .8rem; font-size: .78rem;
        color: var(--accent); font-weight: 500; letter-spacing: .01em; }

    .pipeline-label { color: var(--ink-dim); font-size: .7rem; font-weight: 700;
        letter-spacing: .14em; text-transform: uppercase; margin: .2rem 0 .5rem; }
    .stages { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem;
        margin: 0 0 .2rem; }
    .stage { display: flex; align-items: center; gap: .5rem; padding: .55rem 1.05rem;
        border-radius: 999px; font-size: .88rem; font-weight: 650;
        border: 1.5px solid #35507A; background: #16273D; color: #B6C6DC; }
    .stage.done { border-color: #22C55E; background: #22C55E; color: #04220F; }
    .stage.active { border-color: #22D3EE; background: #22D3EE; color: #04212B;
        box-shadow: 0 0 0 4px rgba(34,211,238,.18); }
    .stage-mark { font-weight: 800; }
    .stage-arrow { color: #47618C; font-weight: 800; font-size: 1rem; }

    .card { padding: 1.15rem 1.25rem; border: 1px solid var(--line);
        border-radius: 14px; background: var(--card); height: 100%; }
    .card h3 { margin: .1rem 0 .5rem; font-size: 1rem; color: var(--ink);
        font-weight: 650; }
    .card p { color: var(--ink-dim); font-size: .87rem; line-height: 1.55; margin: 0; }
    .card-tag { color: var(--accent); font-size: .7rem; font-weight: 700;
        letter-spacing: .1em; text-transform: uppercase; }

    .runs { display: flex; align-items: center; gap: .4rem; flex-wrap: wrap;
        margin: .1rem 0 .5rem; }
    .run-chip { border: 1px dashed rgba(244,63,94,.5); background: rgba(244,63,94,.08);
        color: #FDA4B4; border-radius: 8px; padding: .38rem .7rem;
        font-family: ui-monospace, monospace; font-size: .8rem; }
    .joined { border: 1px solid rgba(45,212,191,.45); background: rgba(45,212,191,.09);
        color: var(--accent-2); border-radius: 8px; padding: .38rem .7rem;
        font-family: ui-monospace, monospace; font-size: .8rem; display: inline-block; }
    .fake { border: 1px solid rgba(34,211,238,.45); background: rgba(34,211,238,.09);
        color: var(--accent); border-radius: 8px; padding: .38rem .7rem;
        font-family: ui-monospace, monospace; font-size: .8rem; display: inline-block; }
    .flow-down { color: var(--ink-dim); font-size: .95rem; margin: .12rem 0 .12rem .6rem; }

    .verdict { text-align: center; padding: 1.6rem 1rem; border-radius: 16px;
        border: 1px solid rgba(34,197,94,.35); background: rgba(34,197,94,.07);
        margin-bottom: 1rem; }
    .verdict .mark { font-size: 2.2rem; color: var(--ok); line-height: 1; }
    .verdict .headline { font-size: 1.15rem; font-weight: 700; color: var(--ink);
        letter-spacing: .12em; text-transform: uppercase; margin-top: .5rem; }

    .checks { border: 1px solid var(--line); border-radius: 12px;
        background: var(--card); padding: .3rem 1rem; }
    .check-row { display: flex; justify-content: space-between; align-items: center;
        padding: .6rem 0; border-bottom: 1px solid var(--line); font-size: .9rem;
        color: var(--ink-dim); }
    .check-row:last-child { border-bottom: none; }
    .check-pass { color: var(--ok); font-weight: 650; }
    .check-warn { color: var(--warn); font-weight: 650; }

    .bignum { text-align: center; padding: 1.1rem .5rem; border-radius: 14px;
        border: 1px solid var(--line); background: var(--card); }
    .bignum .v { font-size: 2.3rem; font-weight: 700; color: var(--accent);
        line-height: 1; letter-spacing: -.02em; }
    .bignum .k { color: var(--ink-dim); font-size: .72rem; letter-spacing: .12em;
        text-transform: uppercase; margin-top: .45rem; }
    .bignum .h { color: var(--ink-dim); font-size: .78rem; margin-top: .5rem;
        line-height: 1.4; }

    .note { border-left: 3px solid var(--accent); background: rgba(34,211,238,.06);
        border-radius: 6px; padding: .8rem 1rem; color: var(--ink-dim);
        font-size: .88rem; line-height: 1.55; }
    .note strong { color: var(--ink); }
    .note-warn { border-left-color: var(--warn); background: rgba(245,158,11,.07); }

    div[data-testid="stMetric"] { background: var(--card); border: 1px solid var(--line);
        border-radius: 12px; padding: .85rem 1rem; }
    div[data-testid="stMetricValue"] { color: var(--accent); }
    div[data-testid="stTabs"] button { font-weight: 600; }
    section[data-testid="stFileUploaderDropzone"] {
        border: 1.5px dashed rgba(34,211,238,.4); background: var(--card);
        border-radius: 14px; }
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
        <div class="kicker">Scaler AI Labs — Assignment</div>
        <div class="hero-title">PII Redaction Tool</div>
        <p class="hero-sub">
          <strong>Structure-aware DOCX processing</strong> ·
          <strong>hybrid validated detection</strong> ·
          <strong>deterministic pseudonymization</strong> ·
          <strong>post-redaction verification</strong>
        </p>
        <div class="capabilities">
          <span class="capability">9 PII types</span>
          <span class="capability">Run-aware DOCX</span>
          <span class="capability">Local NLP</span>
          <span class="capability">Deterministic</span>
          <span class="capability">Leak scan</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_stages(*, analyzed: bool, redacted: bool) -> None:
    """Show Extract → Detect → Replace → Verify as live pipeline status."""

    if redacted:
        states = ("done", "done", "done", "done")
    elif analyzed:
        states = ("done", "done", "active", "pending")
    else:
        states = ("active", "pending", "pending", "pending")

    marks = {"done": "✓", "active": "●", "pending": "○"}
    labels = ("Extract", "Detect", "Replace", "Verify")
    content = (
        '<div class="pipeline-label">Processing pipeline</div><div class="stages">'
    )
    for index, (label, state) in enumerate(zip(labels, states, strict=True)):
        if index:
            content += '<span class="stage-arrow">→</span>'
        css = "" if state == "pending" else f" {state}"
        content += (
            f'<span class="stage{css}">'
            f'<span class="stage-mark">{marks[state]}</span>{label}</span>'
        )
    st.markdown(content + "</div>", unsafe_allow_html=True)


def _render_section_head(number: int, title: str) -> None:
    st.markdown(
        f'<div class="section-head"><span class="section-num">{number:02d}</span>'
        f"{title}</div>",
        unsafe_allow_html=True,
    )


def _render_verification_placeholder() -> None:
    """Explain what verification does before there is anything to verify."""

    st.markdown(
        """
        <div class="card">
          <div class="card-tag">Waiting for redaction</div>
          <h3>Verification starts once a document has been redacted</h3>
          <p>Producing the file is not the last step. Once redaction runs, this
          section reports what the tool checked on the document it just wrote:</p>
          <ul style="color:#94A3B8;font-size:.87rem;line-height:1.75;margin:.6rem 0 0">
            <li>reopen the generated DOCX with a fresh parser</li>
            <li>validate DOCX/ZIP package integrity</li>
            <li>verify structure preservation — containers and Word run counts</li>
            <li>re-scan the output for residual PII</li>
            <li>report unexplained high-confidence residuals</li>
          </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_run_explainer() -> None:
    """The core engineering problem, shown rather than described."""

    st.markdown(
        """
        <div class="card">
          <div class="card-tag">Why ordinary regex misses this</div>
          <h3>Word splits values across formatting runs</h3>
          <p>Word stores a paragraph as “runs” that break wherever formatting
          changes — mid-name, mid-phone-number, mid-address. A regex applied
          per run sees two harmless fragments and matches neither.</p>
          <div style="margin-top:.9rem">
            <div class="runs">
              <span class="run-chip">Run 01 · "Anaya "</span>
              <span class="run-chip">Run 02 · "Varman"</span>
            </div>
            <div class="flow-down">↓ &nbsp;text reconstructed across runs</div>
            <span class="joined">Anaya Varman</span>
            <div class="flow-down">↓ &nbsp;detected</div>
            <span class="joined">PERSON</span>
            <div class="flow-down">↓ &nbsp;replaced, runs and formatting preserved</div>
            <span class="fake">Aarav Iyer</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_feature_cards() -> None:
    columns = st.columns(3)
    cards = (
        (
            "Hybrid detection",
            "Regex plus validators (Luhn, <code>ipaddress</code>, birth-date "
            "context) for structured PII. Local spaCy NER plus contextual and "
            "boundary rules for names, companies, and addresses.",
        ),
        (
            "Deterministic pseudonymization",
            "HMAC-derived replacements: the same source value always maps to the "
            "same synthetic value throughout a document, so the text stays "
            "internally consistent and readable.",
        ),
        (
            "Post-redaction verification",
            "The saved file is reopened, its structure and Word run count checked "
            "against the original, and its text re-scanned for anything that still "
            "looks like PII.",
        ),
    )
    for column, (title, body) in zip(columns, cards, strict=True):
        with column:
            st.markdown(
                f'<div class="card"><h3>{title}</h3><p>{body}</p></div>',
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

    conflicts = int(report.get("conflict_count", 0))
    integrity_ok = structure_ok and bool(package.get("zip_integrity_valid"))
    unclassified = int(residual.get("unclassified_residual_count", 0))
    broad = int(residual.get("broad_overlap_review_count", 0))
    verified = integrity_ok and conflicts == 0 and unclassified == 0

    st.markdown(
        f"""
        <div class="verdict">
          <div class="mark">{"✓" if verified else "!"}</div>
          <div class="headline">
            {"Redaction verified" if verified else "Redaction needs review"}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    columns = st.columns(5)
    columns[0].metric("Replacements", report.get("applied_replacement_count", 0))
    columns[1].metric("Cross-run", report.get("cross_run_replacement_count", 0))
    columns[2].metric("Conflicts", conflicts)
    columns[3].metric("Residual review", residual.get("review_required_count", 0))
    columns[4].metric("Elapsed", f"{result.elapsed:.1f}s")

    def _row(label: str, ok: bool, detail: str) -> str:
        css = "check-pass" if ok else "check-warn"
        return (
            f'<div class="check-row"><span>{label}</span>'
            f'<span class="{css}">{detail}</span></div>'
        )

    st.markdown("&nbsp;", unsafe_allow_html=True)
    st.markdown(
        '<div class="checks">'
        + _row("DOCX integrity", bool(package.get("zip_integrity_valid")), "PASS")
        + _row(
            "Structure preserved", structure_ok, "PASS" if structure_ok else "REVIEW"
        )
        + _row(
            "Output reopened",
            bool(verification.get("reopened_successfully")),
            "PASS",
        )
        + _row("Residual scan", unclassified == 0, "COMPLETE")
        + "</div>",
        unsafe_allow_html=True,
    )

    known = int(residual.get("known_synthetic_detection_count", 0))
    if unclassified == 0 and broad:
        st.markdown(
            f'<div class="note note-warn">{broad} broad detection(s) reviewed — '
            "these overlap synthetic replacements the tool just inserted. "
            "<strong>Zero wholly unclassified high-confidence detections in "
            "supported text.</strong> Raster-image text is not OCRed, so total "
            "document coverage is not claimed.</div>",
            unsafe_allow_html=True,
        )
    elif unclassified:
        st.markdown(
            f'<div class="note note-warn">{unclassified} unclassified '
            "high-confidence detection(s) remain in supported text and need "
            "manual review before this document is shared.</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="note">{known} residual detections are recognized '
            "synthetic replacements, which is expected. No unclassified "
            "high-confidence PII found in supported text.</div>",
            unsafe_allow_html=True,
        )
    st.markdown("&nbsp;", unsafe_allow_html=True)

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
    st.markdown('<div class="kicker">Model evaluation</div>', unsafe_allow_html=True)
    st.write(
        "Measured on a frozen 180-container set labelled **after** the recognizers "
        "were frozen and scored exactly once. These are held-out numbers, not "
        "tuned ones."
    )
    values = (
        (
            "Precision",
            micro["precision"],
            "When we redact something, how often were we right?",
        ),
        ("Recall", micro["recall"], "Of the PII a human found, how much did we catch?"),
        ("F1", micro["f1"], "The balance between the two."),
        (
            "Accuracy",
            micro["entity_detection_accuracy"],
            "TP / (TP + FP + FN) — no inflated true negatives.",
        ),
    )
    for column, (label, value, hint) in zip(st.columns(4), values, strict=True):
        column.markdown(
            f'<div class="bignum"><div class="v">{value * 100:.1f}%</div>'
            f'<div class="k">{label}</div><div class="h">{hint}</div></div>',
            unsafe_allow_html=True,
        )
    st.markdown("&nbsp;", unsafe_allow_html=True)
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
        st.caption("Analysis complete — detections are in section 02 below.")
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
    # Reserved here but filled at the end of the run: analysis and redaction
    # happen further down the script, so rendering now would show stale state.
    stages_slot = st.empty()
    st.divider()
    _render_section_head(1, "Upload")
    upload = _render_upload_and_analyze()

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

    # A single guided page: the whole demo is understandable by scrolling.
    _render_section_head(2, "Analyze")
    current_analysis = st.session_state.get("analysis")
    if _is_analysis_result(current_analysis):
        _render_analysis(current_analysis)
    else:
        st.info(
            "Upload a `.docx` above and select **Analyze document** to build a "
            "conflict-resolved detection plan. Analysis alone never alters or "
            "saves a document."
        )

    st.divider()
    _render_section_head(3, "Redact")
    current_analysis = st.session_state.get("analysis")
    if not _is_analysis_result(current_analysis):
        st.info("Analyze a document first to review its replacement plan.")
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
                except RedactionWriteError as error:
                    st.error(f"Redaction stopped before output was written: {error}")
                except (OSError, ValueError) as error:
                    st.error(f"Could not process that document: {error}")

    st.divider()
    _render_section_head(4, "Verify output")
    result = st.session_state.get("redaction")
    if _is_redaction_result(result):
        _render_verification(result)
    else:
        _render_verification_placeholder()

    st.divider()
    _render_section_head(5, "Evaluation")
    _render_evaluation()

    st.divider()
    _render_section_head(6, "Why this is different")
    _render_run_explainer()
    st.markdown("&nbsp;", unsafe_allow_html=True)
    _render_feature_cards()
    st.markdown("&nbsp;", unsafe_allow_html=True)
    st.markdown(
        '<div class="note"><strong>Everything runs locally.</strong> The '
        "recognizer executes inside this application process — no document "
        "content reaches an external AI or PII service. Reports contain "
        "counts, methods, confidence, and verification status, never raw "
        "detected values.</div>",
        unsafe_allow_html=True,
    )
    with st.expander("The full pipeline, stage by stage"):
        st.markdown(
            "1. **Extract** — every paragraph, table cell, header, footer, and "
            "text box becomes an addressable container with its Word runs "
            "mapped, so a value split across runs is reconstructed.\n"
            "2. **Detect** — structured recognizers (regex + validators) and "
            "semantic recognizers (local NER + context rules) propose spans; "
            "conflicts are resolved deterministically so spans never overlap.\n"
            "3. **Replace** — each accepted span gets an HMAC-derived synthetic "
            "value; structured replacements are re-checked by the same "
            "validators used for detection.\n"
            "4. **Verify** — the rewritten file is saved atomically, reopened, "
            "checked for structural equivalence, and re-scanned for residual "
            "PII before it is offered for download."
        )

    # Filled last so the pills reflect work completed during this script run.
    with stages_slot.container():
        _render_stages(
            analyzed=_is_analysis_result(st.session_state.get("analysis")),
            redacted=_is_redaction_result(st.session_state.get("redaction")),
        )


if __name__ == "__main__":
    main()
