# PII Redaction Tool

The project is complete through **Phase 2D semantic repair**. It extracts DOCX
text—including paired DrawingML/VML text boxes—into stable containers, detects
structured and semantic PII, creates keyed deterministic synthetic values, and
preflights a replacement plan without printing raw values or writing a DOCX.
Full-document redaction is deliberately blocked pending a final blind semantic
evaluation.

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

The extractor creates one `TextContainer` per supported paragraph in the body,
a table cell, a distinct header/footer part, or a paired text box. Each has a
deterministic schema-1.0 ID, reconstructed logical text, and a map back to its
OOXML runs. Shared headers/footers are traversed once; table cells and nested
tables are recursive; hyperlink runs are included. Equal DrawingML choice and
VML fallback text is detected once and rewritten in both representations.

For a cross-run replacement, unaffected prefixes and suffixes stay in their
original runs, replacement text is inserted once in the first affected run,
and covered text is removed from later runs. Runs and paragraph structure are
not flattened. If the source span has mixed formatting, the replacement
inherits the first affected run's formatting. A run containing unsupported
embedded XML is rejected before mutation rather than silently losing content.

## Recognizers

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

Semantic detection uses the local `en_core_web_sm` pipeline plus
prospectus-specific rules:

- `PERSON`: PERSON NER plus plausible multi-token name shape and role/contact
  evidence, including guarded recovery of ORG-mislabelled Indian names.
- `COMPANY`: precise legal-suffix matching plus ORG NER qualified only by
  candidate-local labels or named commercial structure; generic roles,
  legislation, regulators, trusts, headings, and person-shaped spans are
  excluded.
- `ADDRESS`: postal code, premise/street/locality structure, and optional
  address labels, with FAC/GPE/LOC NER used only as supporting evidence.

A location alone is never an address, an ordinary date is never a DOB, and raw
spaCy output is never accepted without category-specific checks.

## Pipeline

```text
DOCX -> stable containers + logical run maps -> local recognizers
     -> deterministic conflict resolution -> privacy-safe detection report

Quality-gated future:
resolved entities -> deterministic pseudonyms -> run-aware rewrite -> save copy
                  -> re-extract -> residual leak scan -> package audit
```

The supplied prospectus has only been scanned and dry-run planned; it has not
been redacted.

## Reproducible environment

The project runs successfully on the existing CPython 3.13.6 interpreter. No
fallback interpreter was needed.

```bash
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
```

`requirements.txt` contains the runtime set, `requirements-dev.txt` adds
quality tools, and `requirements-lock.txt` records the resolved Python 3.13.6
environment. spaCy 3.8.15 and `en_core_web_sm` 3.8.0 are locally installed and
model inference makes no network calls. Faker remains deferred until
pseudonymization. No phone dependency was added; `phonenumbers` remains an
option only if broader annotated evaluation demonstrates a benefit.

## Commands

Run the privacy-safe hybrid scan:

```bash
.venv/bin/python -m src.main scan "input/Red Herring Prospectus.docx"
```

Build a privacy-safe replacement plan without mutation or output writing:

```bash
.venv/bin/python -m src.main redact "input/Red Herring Prospectus.docx" --dry-run
```

The dry run uses `PII_REDACTION_KEY` when present and otherwise creates an
ephemeral in-process key. A future write-enabled run will require an explicit
secret. Running `redact` without `--dry-run` is currently refused.

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

Development ground truth comprises 53 reviewed containers and 44 annotations.
The Phase 2C holdout contains 120 disjoint reviewed containers and 101
annotations. Raw entity text is omitted. The complete format is in
[the ground-truth schema](evaluation/ground_truth/schema.md).

Primary matching is exact `(container_id, type, start, end)`. Reports will show
per-type and micro TP/FP/FN, precision, recall, and F1, with macro aggregates
only where meaningful. ADDRESS will also receive a separately labelled
one-to-one relaxed-overlap result.

The assignment's ambiguous accuracy is reported as exact entity-set
accuracy (Jaccard): `TP / (TP + FP + FN)`. It has no dominating true-negative
term and therefore cannot appear excellent merely because most prospectus text
is not PII. The initial untouched Phase 2C holdout produced micro TP=70, FP=59,
FN=31, precision 0.543, recall 0.693, and F1 0.609. Its immutable result is
[here](docs/phase2c_holdout_initial_75ce5f8.json).

After development-driven semantic repairs, the old holdout was run once as a
non-blind diagnostic: micro precision 0.791, recall 0.901, and F1 0.843;
COMPANY precision improved from 0.250 to 0.909. This is not a final result, and
PERSON precision remains a concern at 0.580. A fresh 180-container candidate
pool is frozen, disjoint from both earlier datasets, unannotated, and unevaluated.

## Deterministic pseudonymization and planning

All nine required types have keyed type-specific factories. Structured outputs
are checked by the same email, phone, SSN, Luhn, date, and IP validators used by
detection. Synthetic domains/ranges and explicit `Example`/`Synthetic` naming
reduce the chance that generated data represents a real person or organization.
The pseudonymizer retries if normalized output equals the original.

Identity linking is separate from detection. It links PERSON and EMAIL only
when one unique local-part/name match exists inside an explicit local context;
ambiguous or weak cases remain independent. A linked pair derives the same
keyed seed so the synthetic email agrees with the synthetic person's name.

Replacement planning detects overlaps and unsafe Word content, checks repeated
entity consistency, calculates every replacement before mutation, and
preflights all affected runs and text-box mirrors. The full dry run currently
plans 661 replacements, including 400 cross-run spans, with zero structural
conflicts. These counts are detector outputs, not approval to write them.

## Current capability boundary

- COMPANY and ADDRESS improved substantially in the one permitted post-fix old-
  holdout diagnostic, but that set is no longer blind. PERSON still shows
  material false-positive risk, so no final quality claim is made.
- Paragraph/table/header/footer and paired DrawingML/VML text-box flows are
  supported and tested. Shape descriptions and Selection Pane names are audited
  but not safely auto-rewritten; raster images are not OCR'd.
- Pseudonym factories and replacement application are tested on synthetic DOCX
  files but have not been applied to the prospectus.
- OCR, leak scanning of a redacted copy, and a final redacted document remain
  out of scope pending a fresh blind evaluation and an explicit go/no-go gate.
- All processing is local; document text is not sent to external APIs.
