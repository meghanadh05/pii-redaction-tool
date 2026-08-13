# PII Redaction Tool

This repository is at **Phase 1**: the authoritative assignment has been
reviewed, the supplied DOCX has been inspected without modification, and the
core architecture and run-fragment mapping primitives have been scaffolded.
End-to-end detection and redaction are intentionally not enabled yet.

## Assignment scope

The source specification requires a script that reads the supplied document
and writes a redacted DOCX containing realistic fake alternatives for, at
minimum: full names, email addresses, phone numbers, company names,
physical/mailing addresses, SSNs, credit-card numbers, dates of birth, and IP
addresses. Final delivery must include source, the redacted DOCX, a short
approach/trade-off README, and an evaluation report with accuracy, precision,
and recall. Recall, precision, code quality/extensibility, and communication
are evaluation criteria.

The assignment says the attachment is a Red Herring Prospectus but later calls
the input a "ticket log." The only supplied input is the prospectus, so that is
the assumed target. The specification also does not define the denominator for
"accuracy" or its span-matching rules. These and other assumptions are recorded
in [the Phase 1 findings](docs/phase1_findings.md).

## Intended pipeline

```text
DOCX stories -> logical text + run map -> recognizers -> overlap resolution
             -> deterministic pseudonyms -> run-aware replacement -> save copy
             -> re-extract saved copy -> high-confidence residual leak scan
```

Structured types will use regex candidates followed by validators: `ipaddress`
for IPs, Luhn for cards, invalid-range checks for SSNs, and normalization plus
context safeguards for phones. PERSON, COMPANY, and ADDRESS will combine a
local spaCy model with document-specific context. DOB will require a birth
signal; ordinary corporate dates are not DOBs.

Each detection is a typed, immutable `PIIEntity` with a half-open character
span, confidence, recognizer provenance, and evidence metadata. Raw text is
excluded from its representation and default serialization. Recognizers own
explicit categories and can be added without modifying the detection engine.
The conflict resolver gives validated structured evidence precedence over weak
generic NER, then considers confidence, length, category priority, and stable
tie-breakers.

Pseudonyms are keyed by a secret HMAC of a normalized identity. Only the HMAC
key—not raw originals—is used as the persistent in-memory mapping key. A stable
seed is passed to type-specific generators, allowing repeated values and linked
person/email data to stay coherent. The secret will come from the environment;
it will never be committed or written to normal logs.

## DOCX handling policy

Detection must operate on reconstructed logical paragraph/cell strings, never
on individual Word runs. `LogicalText` maps half-open detection spans back to
one or more source runs and projects a replacement into the first affected run
while preserving unaffected run prefixes, suffixes, and formatting.

Phase 2 will recursively enumerate body paragraphs, tables/cells, section
headers, and footers, deduplicating shared story parts. Hyperlinks and text boxes
need OOXML-level traversal because python-docx's public API does not expose all
of them consistently. Text in raster images cannot be redacted by python-docx;
it requires local OCR or explicit manual review. The source file is always
read-only and output must be a different path.

## Evaluation plan

Metrics will be computed only from manually annotated, representative ground
truth. Annotations will use stable story/container identifiers, entity type,
and character spans; raw entity strings need not be copied into the annotation
file. Samples will cover contact details, directors/management, tables, legal
text, finance-heavy sections, and address-heavy sections.

The primary scoring will report TP/FP/FN, precision, recall, and F1 per category
plus micro and meaningful macro aggregates using exact
`(container, type, start, end)` matching. ADDRESS will additionally get a
clearly labelled, one-to-one relaxed overlap score. To satisfy the undefined
assignment request, a character-level binary accuracy can be reported with its
denominator stated explicitly; it will not replace entity precision/recall
because true negatives would dominate it. No metrics exist yet and none are
claimed.

## Dependencies

- Python standard library: regex, `ipaddress`, dataclasses, HMAC/hashlib, ZIP/XML
- `python-docx`: normal DOCX paragraph/table/header/footer reading and writing
- `lxml`: controlled low-level OOXML traversal for gaps in python-docx
- `spaCy`: local-only PERSON/ORG and address/context signals
- `Faker`: realistic values driven by deterministic seeds and mappings
- `pytest`: unit, integration, regression, and negative tests

Presidio is deliberately not included: the assignment benefits from showing
the recognizer, validation, scoring, and conflict-resolution decisions. A
phone-number library remains optional; it should be added only if evaluation
shows the local Indian/international validation rules are insufficient.

The current machine does not yet have python-docx, spaCy, or Faker installed.
No packages were installed in Phase 1. The version ranges in `requirements.txt`
reflect current Python 3.13-capable releases but remain an initial compatibility
policy, to be resolved and locked after a clean environment and compatible
local spaCy model are tested in Phase 2.

## Current commands

From the repository root:

```bash
python3 -m src.main --version
python3 -m pytest
```

The CLI intentionally prints Phase 1 help rather than accepting a redaction
command. This prevents an unfinished detector from producing a falsely safe
document.

## Privacy and logging

Normal logs may contain recognizer names, category counts, spans, and confidence
but never names, full emails/phones/addresses, or identifier values. Evidence
metadata must also avoid raw values. An eventual unsafe debug mode must be
explicit, local, and off by default. The document will not be sent to external
services.
