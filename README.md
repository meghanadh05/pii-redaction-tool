# PII Redaction Tool

This tool reads a Microsoft Word `.docx`, detects the assignment’s nine PII
categories, and writes a structurally validated copy in which detected values
are replaced by realistic synthetic alternatives. The supplied prospectus has
been processed to
[`output/Red_Herring_Prospectus_Redacted.docx`](output/Red_Herring_Prospectus_Redacted.docx).
All processing is local; document contents are not sent to external APIs.

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
contained no positives. Raster-image text is not OCRed; shape metadata is
audited but not rewritten. See the concise
[`evaluation report`](docs/evaluation_report.md),
[`redaction run report`](docs/redaction_run_report.json), and
[`engineering overview`](docs/engineering_overview.md) for details.
