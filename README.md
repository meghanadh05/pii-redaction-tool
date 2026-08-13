# PII Redaction Tool

The project is complete through **Phase 2A**. It can extract supported DOCX
text into stable, run-mapped containers and detect structured PII without
printing raw values. Full-document redaction and PERSON/COMPANY/ADDRESS NER are
intentionally not enabled yet.

## Assignment scope

The authoritative assignment requires fake replacement of full names, emails,
phones, company names, physical/mailing addresses, SSNs, credit cards, dates of
birth, and IP addresses. Company names are treated as an assignment-required
sensitive entity category. Final delivery also requires source, a redacted
DOCX, a concise approach/trade-off README, and an evaluation report containing
accuracy, precision, and recall.

The assignment calls the attachment a Red Herring Prospectus but later calls
the input a "ticket log." No ticket log was supplied, so the prospectus is the
target. Further assumptions and the authoritative extraction are in
[the Phase 1 findings](docs/phase1_findings.md).

## Why run-aware processing matters

The prospectus contains approximately **49,815 Word runs**. Of 4,027 non-empty
logical paragraphs, **2,450 (60.84%) are multi-run**. Structural probes found
phone, address, and name-shaped values crossing run boundaries. A loop such as
`for run in paragraph.runs: regex.sub(...)` therefore cannot provide reliable
detection.

The current extractor creates one `TextContainer` per supported paragraph in
the body, a table cell, a distinct header part, or a distinct footer part. Each
container has a deterministic path-like ID, reconstructed logical text, and a
map back to its OOXML runs. Shared headers/footers are traversed once; table
cells and nested tables are traversed recursively; hyperlink-contained runs are
included in logical text.

For a cross-run replacement, unaffected prefixes and suffixes stay in their
original runs, replacement text is inserted once in the first affected run,
and covered text is removed from later runs. Runs and paragraph structure are
not flattened. If the source span has mixed formatting, the replacement
inherits the first affected run's formatting. A run containing unsupported
embedded XML is rejected before mutation rather than silently losing content.

## Phase 2A recognizers

The following deterministic recognizers are implemented:

- `EMAIL`: practical RFC-like pattern, domain-label checks, punctuation-safe
  spans, URL-userinfo exclusion, and case-folded identity normalization.
- `PHONE`: explicit international prefixes, Indian mobile/trunk conventions,
  grouped labelled international numbers, digit-length checks, and financial/
  identifier context exclusions. Bare arbitrary digit sequences are rejected.
- `SSN`: canonical `AAA-GG-SSSS` form plus zero, reserved-area, and known-invalid
  restrictions.
- `CREDIT_CARD`: 13–19 digit candidates with spaces/hyphens, mandatory Luhn
  validation, and identifier-context exclusions.
- `IP_ADDRESS`: IPv4 and IPv6 candidates finalized and canonicalized by the
  standard-library `ipaddress` module.
- `DOB`: validated supported date format plus explicit nearby `DOB`, `Date of
  Birth`, `Birth Date`, `Born`, or `Born on` evidence. Ordinary document dates
  are rejected.

DOB currently supports `DD/MM/YYYY`, `DD-MM-YYYY`, `YYYY-MM-DD`, `DD Month
YYYY`, and `Month DD, YYYY` with four-digit years. Ambiguous two-digit years,
month-only/year-only forms, and dates without birth context are intentionally
unsupported.

Each accepted `PIIEntity` carries confidence, recognizer provenance, validation
signals, and a normalized representation. Raw and normalized values are
excluded from default representations, serialization, logs, and reports.
Validated structured evidence outranks weak overlaps; remaining conflicts are
resolved by confidence, length, explicit category priority, and stable
tie-breakers. Final spans never overlap.

## Pipeline

```text
DOCX -> stable containers + logical run maps -> local recognizers
     -> deterministic conflict resolution -> privacy-safe detection report

Future:
resolved entities -> deterministic pseudonyms -> run-aware rewrite -> save copy
                  -> re-extract -> residual leak scan -> package audit
```

The supplied prospectus has only been scanned; it has not been redacted.

## Reproducible environment

Phase 2A runs successfully on the existing CPython 3.13.6 interpreter. No
fallback interpreter was needed.

```bash
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
```

`requirements.txt` contains the small runtime set, `requirements-dev.txt` adds
quality tools, and `requirements-lock.txt` records the resolved Python 3.13.6
environment. spaCy and Faker are deferred because Phase 2A does not perform NER
or replacement generation. No phone dependency was added: current rules use
standard-library validation and explicit context; `phonenumbers` remains an
option only if annotated evaluation shows a material precision/recall benefit.

## Commands

Run the privacy-safe structured scan:

```bash
.venv/bin/python -m src.main scan "input/Red Herring Prospectus.docx"
```

The default output contains counts, average confidence, story counts, and
cross-run counts—not entity values. Raw terminal display requires the explicit
unsafe flag and should never be redirected into committed artifacts:

```bash
.venv/bin/python -m src.main scan input/example.docx --unsafe-show-pii
```

Quality gates:

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check src evaluation tests
.venv/bin/ruff format --check src evaluation tests
.venv/bin/mypy src evaluation
.venv/bin/python -m compileall -q src evaluation tests
```

## Evaluation design

Ground truth will comprise a source manifest of exhaustively reviewed
containers and privacy-safer JSONL positive annotations. Raw entity text is not
required; an optional keyed HMAC can validate the reconstructed span without
duplicating PII. The complete format is in
[the ground-truth schema](evaluation/ground_truth/schema.md).

Primary matching is exact `(container_id, type, start, end)`. Reports will show
per-type and micro TP/FP/FN, precision, recall, and F1, with macro aggregates
only where meaningful. ADDRESS will also receive a separately labelled
one-to-one relaxed-overlap result.

The assignment's ambiguous accuracy will be reported as exact entity-set
accuracy (Jaccard): `TP / (TP + FP + FN)`. It has no dominating true-negative
term and therefore cannot appear excellent merely because most prospectus text
is not PII. No ground truth exists yet, so no evaluation metrics are claimed.

## Current capability boundary

- PERSON, COMPANY, and ADDRESS recognizers remain Phase 2B scaffolds; no NER has
  been implemented or tuned.
- Standard paragraph/table/header/footer flows are supported and tested.
  DrawingML/VML text boxes, shape descriptions, raster-image text, and unusual
  field semantics still need explicit OOXML auditing before privacy-complete
  redaction. In this prospectus, ordinary header runs are empty while header
  text is held in shapes/text boxes, so the limitation is material and tracked.
- The actual rewrite engine is tested with synthetic DOCX files but has not been
  applied to the prospectus.
- OCR, full pseudonym factories, manual ground truth, measured metrics, and a
  redacted output document remain out of scope for Phase 2A.
- All processing is local; document text is not sent to external APIs.

