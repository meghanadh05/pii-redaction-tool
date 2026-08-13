# Phase 2C findings

Phase 2C freezes and evaluates an independent holdout, implements deterministic
synthetic replacements and conservative identity linking, and adds a complete
read-only replacement-plan dry run. The holdout exposes a serious semantic
quality problem, so no prospectus redaction was written.

## Frozen holdout

The holdout contains 120 containers disjoint from all 53 development
containers and is tied to source SHA-256
`8b5c93f7642d659e64b51be9f6172c86c2825417f376ca1800ed331515e6f929`,
extractor schema 1.0, and the Phase 2B recognizer snapshot `75ce5f8`. It was
committed at `bc1fe79` before evaluation.

The strata are 40 COMPANY-heavy, 20 management/person, 15 address variants, 15
contact/structured, 15 financial/legal negatives, 8 capitalized headings, and
7 text boxes. Exhaustive review produced 101 labels: 34 PERSON, 24 COMPANY, 19
ADDRESS, 19 EMAIL, and 5 PHONE. There were no real-document SSN, credit-card,
DOB, or IP positives.

## Untouched result

The first and only untouched run is preserved as
`phase2c_holdout_initial_75ce5f8.json`. No recognizer rules or thresholds were
changed after labels were revealed.

| Type | TP | FP | FN | Precision | Recall | F1 | Entity-set accuracy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| PERSON | 21 | 10 | 13 | 0.677 | 0.618 | 0.646 | 0.477 |
| EMAIL | 19 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 |
| PHONE | 5 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 |
| COMPANY | 16 | 48 | 8 | 0.250 | 0.667 | 0.364 | 0.222 |
| ADDRESS exact | 9 | 1 | 10 | 0.900 | 0.474 | 0.621 | 0.450 |
| Micro | 70 | 59 | 31 | 0.543 | 0.693 | 0.609 | 0.438 |

Macro across the five types with ground-truth positives is precision 0.765,
recall 0.752, F1 0.726, and entity-set accuracy 0.630. Relaxed ADDRESS matching
at 0.5 intersection-over-shorter-span is TP=10, FP=0, FN=9, precision 1.000,
recall 0.526, F1 0.690, and accuracy 0.526. Metrics for types without positives
are undefined, not perfect.

The risk-stratified sample intentionally over-represents hard candidates, so
aggregate performance is not an unbiased prevalence estimate. It is still an
appropriate safety gate for redaction.

## Error analysis and COMPANY gate

The severe generalizable issue is paragraph-wide COMPANY context. When legal
prose contains `Company`, unrelated spaCy ORG proposals can be promoted as
companies. False positives include transaction roles, document concepts,
government bodies, regulation titles, trusts, person-as-ORG errors, and spans
that join role prefixes or multiple real entities. The eight COMPANY false
negatives are mainly merged or over-broad boundaries plus a professional firm
without a legal suffix.

PERSON errors concentrate in uppercase/list boundaries, missed final names,
ORG-mislabelled Indian names, and address/institution fragments proposed as
people. ADDRESS misses include low-comma/no-premise formats, OCR-like postcode
characters, incomplete office locations, embedded addresses, and candidates
discarded because they broadly overlap validated phone/email spans. Detailed
privacy-safe patterns are in `phase2c_holdout_error_analysis.md`.

The existing 492 full-document COMPANY candidates are therefore unsafe for
automatic replacement. Thresholds were not changed to improve holdout numbers.

## Pseudonymization and identity linking

`DeterministicPseudonymizer` derives seeds with HMAC-SHA256 over type-specific
normalized values. Repeated normalized values share a cached replacement; raw
source-to-fake mappings are never logged. A factory must produce a non-empty,
validator-compatible value different from the normalized original or the run
fails closed after bounded deterministic retries.

Factories cover all nine types. Email uses `example.com`; phone uses the NANPA
fictional 202-555-01xx block; credit cards use a conventional test prefix plus
a calculated Luhn digit; IPs use RFC documentation ranges; names, companies,
and addresses come from local synthetic components; SSNs pass the project's
range validator; and DOBs are valid past dates formatted like their source.

`IdentityLinker` is independent of detection. It links a PERSON and EMAIL only
when their normalized name/local-part relationship is unique within an
explicit local context (one table row or one container). Ambiguous and weak
matches remain unlinked. Linked entities share an opaque keyed identity seed,
allowing a synthetic name and `first.last@example.com` email to agree. The
actual prospectus dry run found no sufficiently confident resolved link after
the current detector/conflict stage; no relationship was forced.

## Replacement plan and dry run

Planning occurs before mutation. It checks source spans, repeated-entity
consistency, overlap conflicts, run mappings, unsupported Word run content,
and mirrored text-box representations. Application requires a conflict-free
plan and re-preflights every container before the first mutation. Synthetic
tests cover body, tables, headers, cross-run spans, and mirrored text boxes.

The privacy-safe command
`python -m src.main redact input.docx --dry-run` inspected all 4,772 containers
and planned 848 replacements: 243 PERSON, 52 EMAIL, 36 PHONE, 492 COMPANY, and
25 ADDRESS. Of these, 484 cross run boundaries. There were zero structural
plan conflicts and no PII-bearing text-box candidates, so no mirror update was
needed for this source. No document object was mutated, no output was written,
and the source hash remained unchanged. The report explicitly states
`BLOCKED_BY_UNTOUCHED_HOLDOUT`.

## Decision and remaining risks

Do not proceed to final redaction. The next work should treat the holdout as
read-only evidence, repair the general rules on development data plus new
non-holdout diagnostic examples, add boundary-aware/local-context COMPANY and
ADDRESS candidates, and create a new append-only post-fix evaluation result.
The original untouched result must remain prominent.

Other risks remain: absent real-document positives for four structured types,
finite synthetic value spaces, missing link opportunities across cautiously
separated containers, shape metadata that is audit-only, complex Word fields,
embedded objects, and raster-image text excluded from OCR.

## Verification

The final Phase 2C gate passed 132 pytest tests, Ruff format and lint, mypy,
compile/import checks, `pip check`, and spaCy model validation. The assignment
and prospectus both pass DOCX ZIP integrity checks and retain their recorded
SHA-256 hashes. `output/` contains only `.gitkeep`; no redacted document exists.
