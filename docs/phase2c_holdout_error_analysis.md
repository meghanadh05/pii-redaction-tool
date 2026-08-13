# Initial holdout error analysis

This analysis belongs to immutable untouched result
`phase2c_holdout_initial_75ce5f8`. The holdout was frozen at commit `bc1fe79`
against Phase 2B recognizers at `75ce5f8`. No threshold or detection rule was
changed after the labels were revealed.

## Severe generalizable issue: COMPANY

COMPANY exact precision is 0.250 (TP=16, FP=48, FN=8). The current recognizer
uses a paragraph-wide company-context boolean. Once a container mentions a
generic word such as `Company`, other spaCy ORG proposals anywhere in that
container can receive enough evidence. In company-heavy legal prose this
promotes transaction roles, document concepts, regulators, regulations, and
other capitalized organizational phrases that are not assignment-defined
company names.

Observed false-positive patterns, stated without raw PII values:

- generic transaction roles such as lead-manager, registrar, bidder, banker,
  shareholder, exchange, auditor, and fund categories;
- corporate/legal document concepts and financial-statement labels;
- government departments, legislation, and regulation titles;
- named family trusts, which are organizations but not companies under the
  annotation policy;
- personal names mislabelled ORG in a paragraph containing company context; and
- over-broad spans that combine a role prefix, multiple entities, or intervening
  text with a real company name.

The eight COMPANY false negatives are dominated by boundary errors: two named
companies joined into one prediction, generic prefixes included with the name,
or a real professional firm without a legal suffix. This explains why the
full-document count of 492 COMPANY candidates cannot safely drive redaction.
The risk-stratified precision cannot be extrapolated as whole-document
prevalence, but it is sufficient to block full redaction.

## PERSON

PERSON exact results are TP=21, FP=10, FN=13. Main patterns are incomplete name
boundaries in uppercase lists, missed final names in comma/slash-separated
lists, Indian names still labelled ORG without sufficiently local role context,
and address/institution phrases emitted as PERSON. Some boundary errors count
as both one FP and one FN.

## ADDRESS

ADDRESS exact results are TP=9, FP=1, FN=10; relaxed overlap improves to TP=10,
FP=0, FN=9. Misses concentrate in valid mailing addresses without enough
commas/premise keywords, postcode OCR-like characters, incomplete-but-usable
office locations, and an address embedded in longer company prose. One broad
prediction included a professional-firm name in the address boundary. A broad
address candidate that also spans phone/email content can lose entirely to
validated structured entities during conflict resolution.

## Structured categories

EMAIL and PHONE each achieved TP-only results on their holdout positives. The
source holdout contains no SSN, credit-card, DOB, or IP-address positives, so
those categories remain covered by synthetic validator tests rather than real
prospectus recall measurements.
