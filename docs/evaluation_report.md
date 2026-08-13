# PII Redaction Tool — Evaluation Report

## Headline result

The primary result is a **blind evaluation**: 180 containers whose labels were
written after the recognizers were frozen, disjoint from every dataset that
informed development, and scored exactly once.

| Metric | Blind (primary) | Non-blind diagnostic |
| --- | ---: | ---: |
| Precision | **0.675** | 0.843 |
| Recall | **0.839** | 0.901 |
| F1 | **0.748** | 0.871 |
| Entity-set accuracy | **0.597** | 0.771 |

The 0.17 precision gap between the two columns is the cost of having tuned
against the earlier dataset. Both are reported because the difference is the
most informative number in this document: it is a direct measurement of how
much a repeatedly-reused evaluation set overstates performance.

## How the numbers are defined

Primary matching is exact `(container ID, entity type, start, end)`, with one
prediction matched to at most one annotation. "Accuracy" is entity-set accuracy
(Jaccard):

`TP / (TP + FP + FN)`

Token-level accuracy is not used. It would require an arbitrary tokenization and
would be dominated by the vast number of non-PII tokens, so it could look
excellent while missing most entities.

## What counts as PII for scoring

Ticket numbers, order numbers, invoice and page numbers, corporate registration
identifiers (CIN, DIN, SEBI registration, ISIN), financial figures, and ordinary
dates are deliberately **not** treated as PII — they identify a transaction or
document rather than a person. Annotations contain no such spans, so a detector
that redacted them is scored as producing false positives.

Company names *are* treated as PII because the assignment lists them as a
required category. Dates are redacted only with explicit birth context, so an
ordinary date in the prospectus is a true negative, not a missed DOB.

## Blind evaluation

180 containers, 168 annotations, 103 of them explicitly reviewed negatives.
Recognizer commit `15a74a6`. Full machine-readable result:
`blind_evaluation_15a74a6.json`.

| Category | TP | FP | FN | Precision | Recall | F1 | Accuracy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EMAIL | 18 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 |
| PHONE | 22 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 |
| COMPANY | 76 | 18 | 13 | 0.809 | 0.854 | 0.831 | 0.710 |
| ADDRESS (exact) | 16 | 12 | 9 | 0.571 | 0.640 | 0.604 | 0.432 |
| PERSON | 9 | 38 | 5 | 0.191 | 0.643 | 0.295 | 0.173 |
| SSN / CREDIT_CARD / DOB / IP | 0 | 0 | 0 | — | — | — | — |
| **Micro** | **141** | **68** | **27** | **0.675** | **0.839** | **0.748** | **0.597** |

Macro across the five categories with labels: precision 0.714, recall 0.827,
F1 0.746. ADDRESS under relaxed one-to-one overlap matching (≥50% of the
shorter span) is TP=22, FP=6, FN=3 — precision 0.786, recall 0.880, F1 0.830.
The exact result remains primary.

## Error analysis

**PERSON is the serious finding.** Precision fell from 0.674 on the tuned
dataset to **0.191** here. The failure is systematic, not random: 38 false
positives are almost entirely Title-Cased *defined terms* from prospectus
boilerplate — "Selling Shareholders", "Key Managerial Personnel", "Group
Companies", "Equity Shares", "Freehold Land", "Leasehold Land". A legal document
capitalizes defined terms exactly as it capitalizes names, and neither the spaCy
model nor the surrounding role/context heuristics separate the two. The earlier
dataset happened to contain few such phrases, so tuning against it never exposed
the weakness.

The practical consequence is over-redaction, not leakage: no false positive was
a real person, and PERSON recall stayed reasonable at 0.643. For a redaction
tool that is the safer direction to fail, but 4 in 5 PERSON redactions being
wrong makes the output noticeably harder to read.

**ADDRESS fails in two distinct ways.** A few detections swallowed an entire
prose paragraph that merely mentioned a location — a genuine over-reach. The
rest are boundary disagreements: the detector returned "Abhimanshree Society,
Pashan Road, Pune – 411 008" where the annotation began at the premise number
"A29". Relaxed matching recovers most of these (16 → 22 TP), which is why exact
precision 0.571 understates detection and overstates the practical problem.

**COMPANY held up well** at 0.809 precision — the strongest semantic category
and the one most improved by earlier work. Its false positives are mostly
boundary errors rather than invented entities: "India) Limited" from a split of
"Central Depository Services (India) Limited", "Company KSH International
Limited" retaining a role prefix, and generic roles such as "the Refund Bank".

**EMAIL and PHONE were perfect on both datasets** — 40 entities, zero errors.
These are the deterministic recognizers, and the result is consistent with their
regex-plus-validator design.

**SSN, CREDIT_CARD, DOB, and IP_ADDRESS have no positives** anywhere in this
prospectus, so their real-document recall is unmeasured. Their validators are
covered by unit tests (Luhn, IPv4/IPv6, DOB-versus-ordinary-date). Zero labels
must not be read as perfect performance.

## Annotator independence

The blind dataset's containers were selected by a recorded algorithm and were
never inspected during recognizer development, so entity *presence* is
independent. However, the annotator had prior exposure to the recognizer
implementation. Entity presence for EMAIL, PHONE, and PERSON is objective, but
**COMPANY and ADDRESS boundary conventions may be biased toward the detector's
own conventions**. Exact and relaxed ADDRESS results are both reported so the
size of that effect stays visible. A fully independent annotator would
strengthen the ADDRESS and COMPANY numbers specifically.

Conventions were fixed in writing before annotation began and are recorded in
`evaluation/ground_truth/final_candidate_pool/annotation_conventions.md`.

## Dataset history

| Dataset / run | Role | TP | FP | FN | Precision | Recall | F1 | Accuracy |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Phase 2B development | Calibration, 53 containers | 44 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 |
| Phase 2C initial | First untouched holdout | 70 | 59 | 31 | 0.543 | 0.693 | 0.609 | 0.438 |
| Phase 2D post-fix | Non-blind diagnostic | 91 | 24 | 10 | 0.791 | 0.901 | 0.843 | 0.728 |
| Phase 2E | Non-blind, bounded PERSON pass | 91 | 17 | 10 | 0.843 | 0.901 | 0.871 | 0.771 |
| **Blind final** | **Frozen labels, scored once** | **141** | **68** | **27** | **0.675** | **0.839** | **0.748** | **0.597** |

The development row is calibration and is not evidence of generalization. The
Phase 2C initial result is preserved unchanged. Immutable machine-readable
results are in `phase2c_holdout_initial_75ce5f8.json`,
`phase2d_holdout_post_fix_99f9fb5.json`,
`phase2e_person_precision_diagnostic_ecbcbf6.json`, and
`blind_evaluation_15a74a6.json`.

## Why no fixes followed this result

The obvious next move — filtering Title-Cased defined terms out of PERSON —
would very likely lift precision substantially. It was deliberately not done.
Tuning against this dataset would convert it into another non-blind diagnostic
and destroy the only unbiased measurement in this project. The correct sequence
is to fix the defined-term failure using new synthetic diagnostics, then freeze
and annotate a further disjoint pool before measuring again.

Reproduce with:

```bash
.venv/bin/python -m evaluation.run_blind_evaluation \
  "input/Red Herring Prospectus.docx" \
  evaluation/ground_truth/final_candidate_pool
```
