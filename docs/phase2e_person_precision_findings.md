# Phase 2E bounded PERSON precision pass

This phase made one development-only PERSON repair after snapshot `982747d`.
It used the Phase 2B development set plus six new generalized synthetic test
classes. No final-pool labels were inspected or created, and the final pool was
not evaluated. COMPANY, ADDRESS, all structured recognizers, pseudonymization,
and identity linking were unchanged.

## PERSON changes

- Expanded the candidate veto vocabulary for role/title, legal/prose,
  organization, and address morphology.
- Added narrative stops so a local role introduction cannot promote later
  responsibilities or legal prose from the same broad region.
- Required an ORG-labelled separated list to have homogeneous person-shaped
  members unless an explicit local person role qualifies the candidate.
- Added semicolon list splitting and exact trimming of parenthetical or dashed
  role annotations from otherwise valid names.
- Preserved direct local-role recovery of an ORG-mislabelled name and ordinary
  PERSON NER subject to person-shape safeguards.

## New generalized tests

Six invented diagnostic classes cover capitalized titles/legal prose in role
regions, organization/address fragments in a person list, insufficient
ORG-list evidence, explicit local ORG-to-PERSON recovery, long semicolon lists
with role annotations, narrative responsibility boundaries, and false PERSON
NER over legal/organization/address phrases. They do not copy Phase 2C or final
pool strings.

## Development evaluation

The 53-container, 44-annotation development set remains exact: TP=44, FP=0,
FN=0, precision=recall=F1=entity-set accuracy=1.000. PERSON remains TP=14,
FP=0, FN=0. COMPANY remains 13/0/0 and ADDRESS remains 6/0/0 exact and relaxed.

## Single Phase 2C diagnostic comparison

The recognizer was committed as `ecbcbf6` before this diagnostic was executed.
The diagnostic was run once and did not influence the implementation.

| Category | Stage | TP | FP | FN | Precision | Recall | F1 | Accuracy |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| PERSON | Phase 2D | 29 | 21 | 5 | 0.580 | 0.853 | 0.690 | 0.527 |
| PERSON | Phase 2E | 29 | 14 | 5 | 0.674 | 0.853 | 0.753 | 0.604 |
| COMPANY | both | 20 | 2 | 4 | 0.909 | 0.833 | 0.870 | 0.769 |
| ADDRESS exact | both | 18 | 1 | 1 | 0.947 | 0.947 | 0.947 | 0.900 |
| ADDRESS relaxed | both | 19 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 |

Micro exact changed from TP=91, FP=24, FN=10, precision=0.791,
recall=0.901, and F1=0.843 to TP=91, FP=17, FN=10, precision=0.843,
recall=0.901, and F1=0.871. There was no measured recall loss and no COMPANY
or ADDRESS regression. These numbers are non-blind diagnostic evidence, not
final metrics.

## Decision

The bounded change improved PERSON precision without reducing measured recall,
but 14 PERSON false positives remain in the deliberately difficult old
diagnostic and precision is only 0.674. No further tuning on Phase 2C is
permitted. Opening the sole final blind holdout now would consume it while the
known precision signal remains weak. The recommendation is therefore not to
open it yet. A future phase should decide an explicit PERSON go/no-go target and
either accept the current conservative limitation or introduce an independent
new development source; it must not tune again on Phase 2C or inspect the final
pool prematurely.
