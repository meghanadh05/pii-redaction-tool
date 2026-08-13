# Ground-truth annotation schema

Phase 2B will store annotations as UTF-8 JSON Lines. The annotation set is tied
to one immutable source DOCX by SHA-256 and to the extraction/container-ID
version used to create it.

Two files are planned:

1. `manifest.json` identifies the source hash, extraction schema version, and
   the containers selected for exhaustive annotation. A selected container with
   no annotation records is an explicitly reviewed negative container.
2. `annotations.jsonl` contains one positive PII entity per line.

Predictions must be filtered to the exhaustively annotated container set before
scoring. Otherwise detections in unreviewed areas would be incorrectly counted
as false positives.

## Manifest shape

```json
{
  "schema_version": "1.0",
  "document_sha256": "<64 lowercase hex characters>",
  "extraction_version": "0.2.0-phase2a",
  "annotation_status": "in_progress",
  "containers": [
    {
      "container_id": "body/t0004/r0002/c0001/p0000",
      "review_complete": true,
      "sample_stratum": "contact_table"
    }
  ]
}
```

`review_complete` must be true before a container is eligible for evaluation.
The sample strata should eventually cover contact information,
directors/management, tables, legal prose, financial-heavy negatives, and
address-heavy content.

## Annotation record

```json
{
  "container_id": "body/t0004/r0002/c0001/p0000",
  "entity_type": "EMAIL",
  "start": 10,
  "end": 32,
  "value_hmac": "optional keyed HMAC-SHA256 hex digest"
}
```

Rules:

- `container_id` is one stable ID emitted by `iter_text_containers` for this
  source hash and extraction version.
- `entity_type` is one of `PERSON`, `EMAIL`, `PHONE`, `COMPANY`, `ADDRESS`,
  `SSN`, `CREDIT_CARD`, `DOB`, or `IP_ADDRESS`.
- `start` and `end` are zero-based Unicode code-point offsets into the exact
  `TextContainer.text`; the interval is half-open and must be non-empty.
- `value_hmac` is optional. When present, it is
  `HMAC-SHA256(annotation_key, entity_type + NUL + normalized_value)`. The key
  comes from a local environment variable, is separate from the redaction key,
  and is never committed.
- Raw `text` is not required and should normally be omitted. An optional raw
  field makes review more convenient but duplicates sensitive data and makes
  ground-truth files harder to handle safely. Local validation can instead
  reconstruct the span from the immutable source and compare the optional
  keyed digest.
- Unkeyed hashes are not acceptable for low-entropy values such as phone
  numbers or dates because they are vulnerable to enumeration.

## Matching and metrics

Primary matching uses exact
`(container_id, entity_type, start, end)` equality with one prediction matched
to at most one annotation. Reports will show TP, FP, FN, precision, recall, and
F1 per category, plus micro totals and macro averages only across categories
with relevant ground truth. ADDRESS will additionally receive a separately
labelled, one-to-one relaxed-overlap score; it will not replace exact results.

The assignment's otherwise undefined accuracy will be reported as exact entity
set accuracy, also known as the Jaccard index:

```text
Entity Detection Accuracy = TP / (TP + FP + FN)
```

This definition treats the set of exact predicted and annotated entities as the
evaluation universe. It avoids the enormous, misleading true-negative count
created by token- or character-level accuracy across mostly non-PII text. If
the union is empty, the value is reported as undefined or excluded from macro
aggregation rather than used to claim perfect performance.

No ground truth or measured metrics are included in Phase 2A.
