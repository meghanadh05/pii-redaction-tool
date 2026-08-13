# PII Redaction Tool

This tool reads a Microsoft Word `.docx`, detects the assignment’s nine PII
categories, and writes a structurally validated copy in which detected values
are replaced by realistic synthetic alternatives. The supplied prospectus has
been processed to
[`output/Red_Herring_Prospectus_Redacted.docx`](output/Red_Herring_Prospectus_Redacted.docx).

Detection never calls an external API: the spaCy model runs in-process wherever
the tool is running. The CLI and the Docker image below keep documents entirely
on your machine. The hosted demo necessarily receives the file you upload —
see [Try it](#try-it).

## Try it

A browser demo lets you upload a `.docx` and download the redacted result along
with a per-type replacement count and the verification report.

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/streamlit run streamlit_app.py    # http://localhost:8501
```

To run it without installing anything into your environment:

```bash
docker build -t pii-redaction .
docker run --rm -p 8501:8501 pii-redaction
```

Uploads are written to a temporary directory, read back into memory, and
deleted before the response is rendered — nothing is kept on disk and no
document text is logged. Each request uses a fresh pseudonymization key, so
replacements are consistent within one document but not linkable across
requests.

**Deploying to Streamlit Community Cloud:** select **Python 3.13** under
_Advanced settings_ before clicking Deploy. spaCy 3.8 publishes no wheels for
Python 3.14, so the default runtime fails to resolve dependencies, and the
Python version cannot be changed after an app is created.

## Installation

Python 3.13 is supported. Create a virtual environment and install the pinned
runtime, development tools, and local English spaCy model:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
```

## Run

Provide a private stable key of at least 16 bytes. The same key and normalized
source value produce the same synthetic replacement; the key and raw mappings
are never written to reports.

```bash
export PII_REDACTION_KEY='use-a-private-secret-from-your-secret-manager'
.venv/bin/python -m src.main redact \
  "input/Red Herring Prospectus.docx" \
  --output "output/Red_Herring_Prospectus_Redacted.docx"
```

Add `--dry-run` and omit `--output` to build and validate a privacy-safe plan
without modifying or writing a document. `scan` produces detection counts only.

## Approach

EMAIL, PHONE, SSN, CREDIT_CARD, and IP_ADDRESS use regular expressions plus
type-specific validation such as Luhn and `ipaddress`; DOB additionally
requires birth context. PERSON, COMPANY, and ADDRESS combine local spaCy NER
with document-specific context and boundary rules. Validated/confident spans
are resolved before replacement, and every detection retains confidence and
recognizer evidence.

Replacements are derived with HMAC-SHA256 and type-specific factories, so
repeated normalized values remain consistent. Generated structured values pass
their production validators. Conservative local PERSON–EMAIL linking is kept
separate from detection so weak relationships are not forced.

## What is deliberately not redacted

Ticket and order numbers are **not** treated as PII, and neither are other
non-personal business identifiers. They identify a transaction or a document,
not a person, and redacting them would destroy the reader's ability to check
that the rest of the document survived intact. Concretely, these are left
untouched:

| Kept | Example |
| --- | --- |
| Ticket / order numbers | `TKT-2026-004281`, `ORD-771240` |
| Corporate registration IDs | CIN, DIN, SEBI registration, ISIN |
| Ordinary dates | `December 10, 2025` (only dates with birth context are redacted) |
| Financial figures and counts | offer prices, share counts, bid lots |
| Page and invoice numbers | `Page 145 of 372` |

Company names *are* redacted, because the assignment lists them as a required
category. A bare digit sequence is never redacted on shape alone: phone and
credit card candidates must clear length, context, and Luhn checks, so account
and reference numbers do not become false positives.

## Adding a new PII type

The recognizers are independent and registered in one place, so a new category
is four small steps:

1. Add the member to `PIIType` in [`src/models.py`](src/models.py).
2. Add a `Recognizer` subclass in [`src/recognizers/`](src/recognizers/)
   implementing `detect(text) -> list[PIIEntity]`, with `name` and
   `supported_types` class attributes.
3. Register it in `structured_recognizers()` or `semantic_recognizers()` in
   [`src/recognizers/__init__.py`](src/recognizers/__init__.py).
4. Add a replacement factory to `_TYPE_FACTORIES` in
   [`src/pseudonymizer.py`](src/pseudonymizer.py).

Conflict resolution, run-aware DOCX rewriting, reporting, and the evaluation
harness are all type-agnostic and pick the new category up automatically.

## DOCX handling and tradeoffs

Detection operates on reconstructed paragraph/cell text rather than individual
Word runs. Character spans are mapped back to runs, preserving unaffected text
and formatting; tables, headers, footers, hyperlinks, nested tables, and paired
DrawingML/VML text boxes are supported. The write path fails before output on
overlaps or unsupported run XML, saves atomically, reopens the result, validates
ZIP/XML integrity, and performs a residual high-confidence scan.

Semantic detection remains imperfect: PERSON is the largest false-positive
risk, exact ADDRESS boundaries can differ, and real prospectus recall could not
be measured for SSN, CREDIT_CARD, DOB, or IP_ADDRESS because the labelled subset
contained no positives. The semantic rules are intentionally biased toward
English-language, Indian corporate documents, so other locales may have lower
recall. Raster-image text is not OCRed; shape metadata is audited but not
rewritten. See the concise
[`evaluation report`](docs/evaluation_report.md),
[`redaction run report`](docs/redaction_run_report.json), and
[`engineering overview`](docs/engineering_overview.md) for details.
