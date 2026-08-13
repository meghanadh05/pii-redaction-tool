# Phase 2A findings

Phase 2A implements local DOCX extraction/run mapping, deterministic structured
recognition, privacy-safe reporting, and an evaluation annotation schema. It
does not implement semantic NER, redact the supplied prospectus, or report
evaluation metrics.

## Environment and dependencies

- The existing CPython 3.13.6 interpreter was used successfully. No Python 3.12
  fallback was required and no compatibility failure occurred.
- `.venv/` was created locally and is excluded by `.gitignore`.
- Runtime: python-docx 1.2.0 and lxml 6.1.1.
- Development: pytest 9.1.1, Ruff 0.15.22, and mypy 2.1.0.
- spaCy, Faker, Presidio, and phonenumbers were not installed because they are
  unnecessary for this phase.
- Human-readable ranges are split between `requirements.txt` and
  `requirements-dev.txt`; `requirements-lock.txt` records the full resolved
  Python 3.13.6 environment.

## DOCX extraction and rewriting

`TextContainer` binds one deterministic path-like ID to a python-docx
paragraph, its story type, reconstructed `LogicalText`, source `Run` objects,
run fragments, and non-sensitive structural metadata. The extractor:

- preserves body/table document order;
- recursively visits physical table cells and nested tables;
- distinguishes ordinary body, table-cell, header, and footer paragraphs;
- includes runs nested under hyperlinks instead of relying only on
  `paragraph.runs`;
- deduplicates header/footer package parts shared by multiple sections; and
- ties ground-truth IDs to the immutable source hash and extraction version.

Actual prospectus extraction produced 4,680 supported containers: 1,006 body,
3,525 table-cell, 75 header, and 74 footer containers. They contain 49,017
supported runs. This is lower than the 49,815 raw Phase 1 run count because the
supported flow deliberately excludes nested drawing/text-box representations.

The live rewriter projects logical replacements back to actual `Run` objects.
It preserves unaffected first-run prefixes and last-run suffixes, inserts once,
clears only covered portions of later runs, retains paragraph/run structure,
and keeps unrelated formatting. Inserted content uses the first affected run's
format. All changes are calculated and checked before mutation; runs containing
unrecognized embedded XML are refused rather than flattened.

Synthetic DOCX integration tests cover one-, two-, and three-run replacements,
partial endpoints, prefixes/suffixes, multiple replacements, Unicode
punctuation, formatting, tables, headers, footers, saving, reopening, stable
IDs, and shared-header/footer deduplication.

## Recognizers and validation

### EMAIL

A practical ASCII RFC-like pattern supports subdomains, plus aliases, uppercase
forms, and punctuation-adjacent values. Local/domain label shape and length are
checked. URL userinfo/query tokens are excluded. The normalization used for
identity linking is case-folded.

### PHONE

The recognizer accepts explicit international prefixes, Indian mobile prefixes,
grouped Indian trunk landlines, and grouped labelled international numbers.
It checks 8–15 digits, grouping/context, and plausible variation. Bare arbitrary
numbers are rejected. Prefix context for CIN, DIN, ISIN, SEBI registration,
references, monetary/offer/share/page contexts, and currency forms suppresses
false positives. Phone values normalize to digits plus country-code semantics;
bare Indian mobile values normalize with `+91`.

No phonenumbers dependency was added. This is an intentional small-dependency
choice, not a claim that the heuristic covers every country's national format.
Ground-truth errors should drive any later dependency decision.

### SSN

Only canonical `NNN-NN-NNNN` shapes are accepted. Zero areas/groups/serials,
area 666, areas 900–999, and two well-known invalid examples are rejected.

### CREDIT_CARD

Candidates contain 13–19 digits with optional spaces/hyphens. They must pass
Luhn and must not occur in recognized identifier context. Internal
normalization is digits-only.

### IP_ADDRESS

Regex supplies bounded IPv4/IPv6 candidates; `ipaddress.ip_address` is the final
validator and provides the compressed canonical value. Invalid octets and
malformed IPv6 candidates are rejected.

### DOB

Dates are parsed and range-checked, then accepted only with nearby `DOB`, `Date
of Birth`, `Birth Date`, `Born`, or `Born on` evidence before the date, or an
explicit DOB label immediately after it. Supported forms are `DD/MM/YYYY`,
`DD-MM-YYYY`, `YYYY-MM-DD`, `DD Month YYYY`, and `Month DD, YYYY`. Two-digit
years, partial dates, future dates, and dates without birth context are
intentionally unsupported.

Negative tests cover CIN, DIN, SEBI registration identifiers, financial
amounts, share/offer text, page references, arbitrary long numbers, and the
specified corporate/offer/financial/meeting dates.

## Conflict resolution and privacy reporting

The existing deterministic resolver is now exercised with concrete structured
outputs. Tests cover a validated email against a contained weak entity, a
Luhn-valid card overlapping a phone candidate, and a context-qualified DOB
against a weak overlapping detection. Validated/strong-context evidence,
confidence, length, type priority, and stable source tie-breakers determine the
winner; no final overlaps remain.

`python -m src.main scan <docx>` emits only structural counts, accepted counts,
cross-run counts, and average confidence. Normalized metadata and raw values are
not serialized. `--unsafe-show-pii` is the sole CLI opt-in for raw terminal
values. It was not used to create a repository artifact.

## Preliminary real-document scan

The privacy-safe report is stored in `docs/phase2a_detection_report.json` and is
bound to source SHA-256
`8b5c93f7642d659e64b51be9f6172c86c2825417f376ca1800ed331515e6f929`.

| Type | Accepted | Cross-run | Average confidence |
| --- | ---: | ---: | ---: |
| EMAIL | 52 | 0 | 0.9900 |
| PHONE | 36 | 24 | 0.9772 |
| SSN | 0 | 0 | — |
| CREDIT_CARD | 0 | 0 | — |
| IP_ADDRESS | 0 | 0 | — |
| DOB | 0 | 0 | — |

These are detector outputs, not TP/FP/FN or evaluation results. Masked-format
and evidence-distribution auditing found no obvious structured category error,
but only manual ground truth can measure correctness.

## Ground truth and accuracy

`evaluation/ground_truth/schema.md` defines a source manifest plus JSONL entity
records. Selected containers must be exhaustively reviewed; this represents
negative containers without adding fake negative annotations. Raw values are
optional and discouraged. A keyed HMAC of the normalized span may be included
without enabling low-entropy enumeration attacks associated with plain hashes.

Exact matching uses `(container_id, entity_type, start, end)`. The assignment's
accuracy will be explicitly defined as exact entity-set accuracy (Jaccard):

```text
TP / (TP + FP + FN)
```

This avoids misleading token/character true negatives. Precision, recall, and
F1 remain primary. No values are calculated until labelled ground truth exists.

## Remaining limitations and risks

- PERSON, COMPANY, and ADDRESS remain unimplemented scaffolds.
- The prospectus's ordinary header paragraphs contain no text; visible header
  text is largely stored in DrawingML/VML text boxes. Text-box choice/fallback
  pairs, drawing descriptions, and raster images are not yet extracted as
  independently rewritable containers. This is a material coverage gap that
  must be closed or explicitly reviewed before final redaction.
- Complex Word fields and embedded objects are not rewritten. Unsupported run
  content fails closed.
- Email matching is ASCII/practical rather than full RFC 5322 or international
  email support.
- Phone recognition intentionally trades recall on unlabelled unfamiliar local
  formats for precision; annotated evidence must determine whether
  `phonenumbers` is justified.
- DOB numeric day/month order is interpreted as day-first for slash/hyphen
  forms, consistent with the India-focused document.
- Stable container IDs are stable only for the same source structure and
  extraction version; both are captured in the ground-truth manifest.
- Normalized values still exist in process memory for entity linking and must
  be treated as sensitive even though default logging excludes them.
- No redacted prospectus, OCR result, ground truth, or measured evaluation
  metric exists yet.

## Verification

- pytest: 99 passed.
- Ruff lint: passed.
- Ruff format check: passed.
- mypy: passed across all 32 source and test files.
- Python compile/import checks: passed.
- `pip check`: passed in the Python 3.13.6 virtual environment.
- Both source DOCX packages passed ZIP integrity checks.
- The committed privacy-safe JSON report exactly matches a fresh detector run.
- The original assignment and prospectus hashes and modification times remained
  unchanged.
- `output/` contains no redacted document or other generated output.

## Recommended Phase 2B order

1. Close the known OOXML story gap by pairing and testing DrawingML/VML text-box
   choice/fallback content and auditing shape descriptions; define an explicit
   manual-review policy for raster images.
2. Freeze the extractor/container-ID version, select representative containers,
   and manually annotate the Phase 2B development/evaluation baseline before
   tuning semantic recognizers.
3. Evaluate the structured recognizers on the labelled development subset and
   adjust only evidence-backed false positives/negatives; decide whether
   phonenumbers materially helps.
4. Install and verify a local Python 3.13-compatible spaCy model, recording its
   exact version and checksum.
5. Implement PERSON candidates and prospectus-specific context/negative rules,
   then calibrate confidence on development annotations.
6. Implement COMPANY as the assignment-required sensitive category using ORG
   NER, legal suffixes, and precision-focused exclusions.
7. Implement ADDRESS using local NER/postal structure and neighboring-container
   context; retain exact and relaxed evaluation modes.
8. Re-exercise all cross-type conflicts and freeze thresholds without tuning on
   the held-out evaluation subset.
9. Stop for review before full pseudonym generation or prospectus redaction.
