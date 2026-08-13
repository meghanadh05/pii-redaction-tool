# PII Redaction Tool — Evaluation Report

## Scope and interpretation

The primary current-model result below is the latest **post-fix diagnostic** on
the 120-container Phase 2C dataset (101 exhaustive entity annotations). It is
the best honest measured result for the implementation used to generate the
redacted document, but it is **not a blind final holdout**: Phase 2C labels had
already been examined to identify generalized error classes before the Phase
2D and bounded Phase 2E repairs. The sample is deliberately risk-stratified
toward difficult legal, management, address, contact, financial, heading, and
text-box content, so aggregate metrics are not an unbiased prevalence estimate
for every prospectus paragraph.

The primary match is exact `(container ID, entity type, start, end)`. “Accuracy”
is entity-set accuracy (Jaccard):

`TP / (TP + FP + FN)`

This definition is used because token-level accuracy would require an arbitrary
tokenization and would be dominated by the very large number of non-PII tokens.
It could appear excellent even while missing important entities and would hide
the exact-boundary errors that matter when mutating a DOCX.

## What counts as PII for scoring

Ticket numbers, order numbers, invoice and page numbers, corporate registration
identifiers (CIN, DIN, SEBI, ISIN), financial figures, and ordinary dates are
deliberately **not** treated as PII. They identify a transaction or document
rather than a person. Annotations therefore contain no such spans, and a
detector that redacted them would be scored as producing false positives.

Company names *are* treated as PII because the assignment lists them as a
required category. Dates are redacted only with explicit birth context, so an
ordinary date in the prospectus is a true negative, not a missed DOB.

## Current model: Phase 2E post-fix diagnostic

| Category | TP | FP | FN | Precision | Recall | F1 | Entity-set accuracy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| PERSON | 29 | 14 | 5 | 0.674 | 0.853 | 0.753 | 0.604 |
| EMAIL | 19 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 |
| PHONE | 5 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 |
| COMPANY | 20 | 2 | 4 | 0.909 | 0.833 | 0.870 | 0.769 |
| ADDRESS (exact) | 18 | 1 | 1 | 0.947 | 0.947 | 0.947 | 0.900 |
| SSN | 0 | 0 | 0 | — | — | — | — |
| CREDIT_CARD | 0 | 0 | 0 | — | — | — | — |
| DOB | 0 | 0 | 0 | — | — | — | — |
| IP_ADDRESS | 0 | 0 | 0 | — | — | — | — |
| **Micro aggregate** | **91** | **17** | **10** | **0.843** | **0.901** | **0.871** | **0.771** |

Macro results across the five categories with positive labels are precision
0.906, recall 0.927, F1 0.914, and entity-set accuracy 0.855. ADDRESS relaxed
one-to-one overlap matching (at least 50% intersection over the shorter span)
is TP=19, FP=0, FN=0, precision=1.000, recall=1.000, F1=1.000, and accuracy=1.000.
The exact result remains primary.

SSN, CREDIT_CARD, DOB, and IP_ADDRESS had no positive examples in the supplied
prospectus evaluation subset, so their real-document recall cannot be measured.
Their regex, contextual safeguards, normalization, and validators are covered
by unit tests, including Luhn, IPv4/IPv6 validation, and DOB-versus-ordinary-date
negatives. Zero labels for these categories must not be interpreted as perfect
real-world performance.

## Development and evaluation history

| Dataset/run | Role | TP | FP | FN | Precision | Recall | F1 | Accuracy |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Phase 2B development | Calibration: 53 containers, 44 labels | 44 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 |
| Phase 2C initial | First untouched holdout run | 70 | 59 | 31 | 0.543 | 0.693 | 0.609 | 0.438 |
| Phase 2D post-fix | Non-blind diagnostic | 91 | 24 | 10 | 0.791 | 0.901 | 0.843 | 0.728 |
| Phase 2E current | Non-blind bounded PERSON diagnostic | 91 | 17 | 10 | 0.843 | 0.901 | 0.871 | 0.771 |

Development scores are calibration results and are not evidence of independent
generalization. The Phase 2C initial result remains preserved unchanged. The
Phase 2D/2E figures show the measured effect of generalized repairs but are
explicitly diagnostic rather than blind final metrics.

## Error analysis

- **PERSON remains the largest semantic risk.** Local role/list recovery raised
  recall, but capitalized prose, role fragments, and ORG-mislabelled spans can
  still produce false positives. The bounded precision pass reduced PERSON FP
  from 21 to 14 without changing TP or FN, but precision remains 0.674.
- **COMPANY improved substantially** after paragraph-wide promotion was removed
  and replaced by candidate-local evidence, precise legal suffixes, role/legal/
  government exclusions, and boundary trimming. Precision improved from 0.250
  in the initial holdout to 0.909 in the post-fix diagnostic.
- **ADDRESS exact boundaries remain fallible.** Relaxed overlap is complete on
  this subset, but one exact FP/FN boundary pair remains; replacement scope can
  therefore still be broader or narrower than a human annotation.
- **EMAIL and PHONE performed strongly** on the labelled subset with no measured
  FP or FN. This does not establish performance outside the represented formats.

The complete immutable and append-only machine-readable results are in
`phase2c_holdout_initial_75ce5f8.json`,
`phase2d_holdout_post_fix_99f9fb5.json`, and
`phase2e_person_precision_diagnostic_ecbcbf6.json` in this directory.

## The blind evaluation this report does not contain

Because every dataset above has now informed a repair, none of them can produce
an unbiased final number. The instrument for one already exists and is frozen:
`evaluation/ground_truth/final_candidate_pool/` holds 180 containers selected by
a recorded algorithm, disjoint from all 53 development and 120 Phase 2C
containers, with `annotation_status: not_started` and `evaluation_status:
not_run`. Its manifest pins the source, extractor, and recognizer commit hashes.

Exhaustively annotating that pool and scoring it exactly once would give the
first genuinely blind measurement of this implementation. It has deliberately
not been run, because a blind evaluation is only blind the first time and the
recognizers were still being repaired. The expected outcome is a micro precision
somewhere between the untouched Phase 2C result (0.543) and the current
non-blind diagnostic (0.843); anyone reading these numbers should anchor on that
range rather than on 0.843 alone.
