# Phase 2D findings

Phase 2D repairs semantic detection using the Phase 2B development set and new
generalized diagnostic examples. The immutable Phase 2C result was preserved
byte-for-byte. The Phase 2C labels were used only to identify broad error
classes; no exact holdout string, container ID, or threshold search was used in
the repair tests.

## Recognition changes

Only PERSON, COMPANY, and ADDRESS changed. Structured recognizers and
pseudonymization/linking were not modified.

- COMPANY no longer has paragraph-wide promotion. Precise legal-suffix spans
  are preferred; suffixless NER spans require evidence local to that candidate.
  Role prefixes are trimmed, adjacent legal names are split, suffixes are
  recovered, and whitespace fragmentation is normalized. Generic transaction
  roles, laws/regulations, document concepts, government/regulatory bodies,
  trusts, headings, and person-shaped ORG spans are rejected or down-ranked.
- PERSON uses local management/contact-role evidence and bounded list regions.
  It supports uppercase Indian multi-token names, comma/slash/`and` separators,
  final list members, and guarded recovery of ORG-mislabelled names. Address,
  institution, role-only, and generic-capitalized shapes are excluded.
- ADDRESS scores multiple independent premise, road/locality, region, postcode,
  NER, and local-label signals rather than requiring one comma-heavy template.
  It supports embedded and no-postcode structural addresses, trims a leading
  company span, recognizes an OCR-like postcode variant, and ends before local
  phone/email/site/contact fields so a structured overlap does not discard the
  full address.

## Generalized diagnostic tests

Ten new synthetic diagnostics cover local versus paragraph-wide COMPANY
evidence, adjacent legal entities and role-prefix trimming, a locally labelled
professional firm, adversarial government/regulation/trust/role/person-shaped
ORG negatives, uppercase separated PERSON lists, guarded ORG-to-PERSON
recovery, capitalized address/institution PERSON negatives, low-comma and
embedded/no-postcode addresses, contact-boundary trimming, company-prefix
trimming, and location-only negatives. None copies a Phase 2C container.

## Development evaluation

The calibrated 53-container development set has 44 annotations: 14 PERSON, 13
COMPANY, 6 ADDRESS, 6 EMAIL, and 5 PHONE. Exact evaluation is TP=44, FP=0,
FN=0; precision, recall, F1, entity-set accuracy, and macro metrics are 1.000.
Relaxed ADDRESS is also TP=6, FP=0, FN=0. These are development results, not
independent or final performance.

## Phase 2C pre-fix versus post-fix diagnostic

The initial result remains at
`phase2c_holdout_initial_75ce5f8.json` with SHA-256
`72f7dfdcf861f8b4fa329531745727892f83d7a3ddffdf7b467724b857c5bcf8`.
The post-fix result was run once at recognizer commit `99f9fb5` and saved as a
new append-only artifact. Phase 2C is no longer an untouched final evaluation.

| Category | Stage | TP | FP | FN | Precision | Recall | F1 | Entity-set accuracy |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| PERSON | pre | 21 | 10 | 13 | 0.677 | 0.618 | 0.646 | 0.477 |
| PERSON | post | 29 | 21 | 5 | 0.580 | 0.853 | 0.690 | 0.527 |
| COMPANY | pre | 16 | 48 | 8 | 0.250 | 0.667 | 0.364 | 0.222 |
| COMPANY | post | 20 | 2 | 4 | 0.909 | 0.833 | 0.870 | 0.769 |
| ADDRESS exact | pre | 9 | 1 | 10 | 0.900 | 0.474 | 0.621 | 0.450 |
| ADDRESS exact | post | 18 | 1 | 1 | 0.947 | 0.947 | 0.947 | 0.900 |
| ADDRESS relaxed | pre | 10 | 0 | 9 | 1.000 | 0.526 | 0.690 | 0.526 |
| ADDRESS relaxed | post | 19 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 |
| Micro | pre | 70 | 59 | 31 | 0.543 | 0.693 | 0.609 | 0.438 |
| Micro | post | 91 | 24 | 10 | 0.791 | 0.901 | 0.843 | 0.728 |

The post-fix macro metrics across the five labelled categories are precision
0.887, recall 0.927, F1 0.901, and entity-set accuracy 0.839. EMAIL and PHONE
remain exact. The prospectus holdout still has no real positive SSN,
CREDIT_CARD, DOB, or IP_ADDRESS labels.

## Full-document sanity analysis

The privacy-safe scan resolves 661 candidates: 364 PERSON, 148 COMPANY, 61
ADDRESS, 52 EMAIL, and 36 PHONE. COMPANY fell from 492 to 148 (344 fewer,
69.9%), but the acceptance evidence—not the lower count—is the useful result:
136 accepted spans have a precise legal suffix and 12 use qualified local
NER/commercial structure.

The raw audit considered 1,680 spaCy ORG proposals. It rejected 853 as
role/legal/government/trust/person-shaped, 598 for missing candidate-local
company evidence, and 118 as whole-container headings; 98 were superseded by
more precise suffix spans. This explains the count change without treating it
as measured accuracy.

The current dry run plans all 661 replacements, including 400 cross-run spans,
with zero replacement conflicts, no mutation, and no output write. No resolved
candidate occurs in a text box in this source, so mirrored updates remain
covered by synthetic DOCX tests rather than this run.

## Remaining errors

- PERSON is now recall-oriented but still over-promotes capitalized role/prose
  fragments inside long locally qualified regions and some ORG-labelled list
  fragments. Long lists still create boundary joins/splits. Its post-fix
  precision of 0.580 is the primary blocker.
- COMPANY retains two false positives and four false negatives in the old
  diagnostic, mainly suffixless/local-label evidence and exact boundaries.
- ADDRESS has one exact boundary disagreement: relaxed matching is complete,
  but exact replacement scope remains important.
- Structured categories absent from real-document labels still have only
  synthetic validator coverage. Raster image text and unsafe shape metadata
  remain outside automatic rewriting.

## Fresh final-evaluation candidate pool

The unlabelled pool contains 180 unique containers and is disjoint from all 53
development and 120 Phase 2C containers. Its strata are 40 company/legal prose,
35 management/person, 25 address variants, 20 structured contacts, 25
financial/legal negatives, 15 capitalized headings, 15 text boxes, and 5
general candidates. Selection used only container metadata and detector output;
no labels were inspected and no annotation file exists.

The manifest freezes source SHA-256
`8b5c93f7642d659e64b51be9f6172c86c2825417f376ca1800ed331515e6f929`,
extractor 1.0, recognizer commit `99f9fb5`, selection algorithm
`phase2d-final-pool-v1`, and pool-manifest SHA-256
`ceefe99f45589f911c8b634f85ed9f21a99ae48337013398554e55fa2c6307b9`.
Its annotation status is `not_started` and evaluation status is `not_run`.

## Verification and decision

All 144 pytest tests pass. Ruff lint and format, mypy over `src` and
`evaluation`, compile/import checks, `pip check`, and spaCy validation pass;
`en_core_web_sm` 3.8.0 is compatible with spaCy 3.8.15 on Python 3.13.6. Both
DOCX packages pass ZIP and python-docx load checks. The prospectus and frozen
Phase 2C result retain their recorded hashes, `git diff --check` passes, and
`output/` contains only `.gitkeep`.

Semantic detection is not yet ready to consume the final blind evaluation:
the one permitted old-holdout diagnostic exposes material PERSON precision
risk. The next phase should perform one bounded PERSON-precision pass using
development data and new generalized synthetic diagnostics only, without
opening final-pool labels. Then freeze the resulting recognizer snapshot before
manual exhaustive annotation and a single blind evaluation. Proceed to full
redaction only if that evaluation passes an explicit per-category gate.
