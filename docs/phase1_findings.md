# Phase 1 findings

Inspection date: 2026-08-13 (Asia/Kolkata). All document inspection was local
and privacy-safe; raw document PII was not printed.

## Authoritative assignment

The DOCX says:

- Read the input and produce a redacted version with fake alternatives.
- Detect at minimum full names, emails, phones, company names, physical/mailing
  addresses, SSNs, credit cards, dates of birth, and IP addresses.
- Deliver source code, a redacted DOCX, a short approach/trade-off README, and an
  evaluation explanation/report containing accuracy, precision, and recall.
- Evaluation emphasizes recall, precision (including avoiding non-PII order or
  ticket numbers), code quality/extensibility, and README clarity.
- Any of regex, spaCy/NER, Presidio, or custom logic is acceptable; the stated
  submission window is 24 hours.

### Ambiguities and discrepancies

1. The background calls the attachment a Red Herring Prospectus, while the task
   says to read a "ticket log." No ticket log exists in this repository. The
   supplied prospectus is assumed to be the intended input.
2. "Accuracy" has no denominator, true-negative unit, or span-match definition.
   Entity precision/recall/F1 will be primary; any reported accuracy will state
   its exact unit and denominator.
3. The specification does not define partial-span matching. Exact matching will
   be primary and ADDRESS will also have a separately labelled relaxed score.
4. Company names are not always considered personal data in ordinary privacy
   taxonomies, but they are explicitly mandatory here and will be treated as a
   required redaction category.
5. The Indian prospectus may contain no US SSNs, credit cards, DOBs, or IPs.
   Absence in this file does not remove the detector requirement; synthetic
   unit tests will cover them and metrics will not invent occurrences.
6. "Dates of birth" does not authorize redacting every date. A birth-related
   label or defensible contextual signal is required.
7. The assignment allows a choice about generic ticket/order identifiers. The
   controlling engineering requirement for this project is higher precision,
   so offer values, share counts, ordinary dates, page numbers, SEBI numbers,
   CIN, DIN, and generic references remain unredacted unless they independently
   satisfy a required PII recognizer.
8. Consistency, deterministic pseudonyms, confidence/evidence, leak scans, and
   detailed DOCX handling are not explicitly demanded by the short assignment;
   they are additional controlling engineering requirements for this project.

## Environment and source integrity baseline

- Working directory: `/Users/meg/Projects/pii-redaction-tool`
- Python: 3.13.6 at
  `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3`
- Both required DOCX files exist.
- Prospectus size: 1,844,676 bytes (approximately 1.76 MiB).
- Assignment size: 9,087 bytes.
- No `.venv`, `venv`, or `env` directory existed at inspection time.
- Relevant installed packages: lxml 6.0.2 and pytest 9.0.3. Ruff 0.15.12 and
  mypy 2.1.0 are also available. python-docx, spaCy, Faker, Presidio, and
  phonenumbers were not installed.
- The directory was not a Git working tree, so `git diff` was unavailable.
- Initial assignment SHA-256:
  `328ebfd6c333e88d69c7061a70f21c39b60e6e5615f4a6d4a38c23d91006d0bf`
- Initial prospectus SHA-256:
  `8b5c93f7642d659e64b51be9f6172c86c2825417f376ca1800ed331515e6f929`

## Prospectus structure

Counts were obtained directly from the OOXML package. "Top-level paragraph"
matches the general behavior of `Document.paragraphs`; it excludes table-cell
paragraphs.

| Item | Finding |
| --- | ---: |
| Top-level body paragraphs | 1,006 |
| Table-cell paragraphs | 3,525 |
| Logical body/table paragraphs total | 4,531 |
| Raw `w:p` elements in `document.xml` | 4,561 |
| Non-empty logical paragraphs | 4,027 |
| Top-level tables | 76 |
| Tables including nested tables | 76 |
| Nested tables | 0 |
| Table cells / non-empty table cells | 3,225 / 3,074 |
| Sections (`w:sectPr`) | 85 |
| Runs in body document XML | 48,819 |
| Runs in header parts | 922 |
| Runs in footer parts | 74 |
| Approximate total runs | 49,815 |

Of 4,027 non-empty logical paragraphs, 2,450 (60.84%) contain multiple
runs. The rate is 655/692 (94.65%) outside tables and 1,795/3,335 (53.82%)
inside tables. Run-aware detection is therefore mandatory.

Tables hold about 114,675 of 325,048 extracted body characters (35.28%). They
also contain structured/contact signals, including 12 syntactic email matches
and multiple phone/address/name-labelled candidates. Table text is important,
not incidental.

### Headers, footers, links, and drawing content

- 75 header parts are referenced; 73 contain raw `w:t` text. Together they have
  229 raw paragraph elements, 922 runs, 286 raw text characters (including
  DrawingML/VML choice-fallback copies), and 146 field instruction elements.
  There are five distinct non-empty raw header texts, with one repeated in 69
  parts.
- 74 footer parts are referenced. They contain 74 runs but no ordinary visible
  text in `w:t` nodes.
- No `w:hyperlink` elements, hyperlink relationships, or any external package
  relationships were detected.
- No nested tables were detected.
- The package contains 88 DrawingML drawings, 78 VML picture/shape fallbacks,
  78 VML text boxes, and 156 raw `w:txbxContent` nodes. The doubled text-box
  content count reflects OOXML `AlternateContent` choice/fallback
  representations and must not be treated as 156 independent visible boxes.
  Most are in headers; one shape/text-box pair is in the main document.
- Eight embedded image relationships/media files are present. Text baked into
  them is not exposed as ordinary Word text.
- Across Word XML parts, 98 non-empty drawing/shape `descr` attributes and 119
  non-empty `name` attributes exist. These are not ordinary visible text and
  were not printed or classified, but Phase 2's package audit must treat alt
  text/descriptions as possible residual metadata rather than ignoring them.
- No footnote, endnote, or comment story parts; content controls; tracked-change
  insertion/deletion nodes; or `altChunk` content were detected.
- No non-empty core document-property values were detected.

### Run fragmentation probes

These probes are structural heuristics, not ground truth and not detector
accuracy measurements:

- 52 syntactic email spans were found; none crossed a run boundary in this
  document.
- 51 broad phone-shaped candidates were found; 26 crossed runs. A stricter
  phone-label probe found 30 candidates, 18 crossing runs.
- Eight address-label tail candidates were found; seven crossed runs. Six
  postal-address-shaped candidates were found; all six crossed runs.
- Of 28 name-label tail candidates, 24 crossed runs. Eleven candidate
  paragraphs adjacent to table name headers were found; eight were multi-run.

Thus phone, address, and likely name values are demonstrably fragmented here.
Even though sampled emails happen not to be fragmented, the implementation must
handle that case because Word formatting can split any visible token.

## DOCX replacement strategy

1. Enumerate every relevant story: body paragraphs, recursive table/cell
   paragraphs, distinct header/footer parts, and explicitly audited OOXML text
   boxes. Keep a stable story/container identifier for ground truth and reports.
2. Reconstruct each logical container by walking run-like XML in display order,
   including hyperlink children, tabs, line breaks, and supported field results.
   Do not concatenate unrelated cells or paragraphs. Context recognizers may use
   neighboring containers without changing the target container's offsets.
3. Record a character map from logical offsets to the owning XML run/text node
   and offset within that node. Run all recognizers on the reconstructed text.
4. Validate spans against the exact source substring, resolve overlaps, and
   create non-overlapping replacements before modifying XML.
5. Apply replacements from right to left or via per-run projection. Put a
   cross-run replacement in the first affected run, remove only covered text
   from later runs, and retain unaffected prefixes/suffixes. The replacement
   inherits the first affected run's formatting; exact mixed-format recreation
   is not always meaningful when replacement length differs.
6. Traverse nested tables recursively even though this file currently has none.
   Deduplicate inherited/shared header/footer parts so each XML part is changed
   once.
7. Handle hyperlink display text at the XML child level without changing its
   relationship. Audit text boxes through `w:txbxContent`, updating both active
   and fallback representations coherently where necessary.
8. Save only to a new output path, validate/reopen the ZIP package, extract text
   again, rerun high-confidence recognition, and produce a residual report with
   no raw values. Recheck the source hash after the run.

### python-docx capability boundary

python-docx is suitable for standard paragraphs/runs, table cells, styles,
sections, headers, footers, and saving a new DOCX. Table traversal must still be
recursive; `Document.paragraphs` alone omits table text. Public hyperlink
support varies by version, so raw child-order traversal is safer for a complete
run map.

python-docx does not reliably expose text boxes, VML/floating shapes, drawing
alt text, all field semantics, footnotes/endnotes/comments, or text baked into
images through its public API. Unsupported XML is often preserved when
untouched, but preservation and editable visible text are different guarantees.
This input's substantial header shape/text-box content requires a low-level
lxml audit. Raster images need local OCR/manual review; the tool cannot honestly
claim complete visual redaction without it.

## Current limitations

- Recognizer category modules are explicit Phase 2 scaffolds and raise
  `NotImplementedError`; the CLI cannot redact.
- No spaCy model has been selected, downloaded, or evaluated.
- The run projector is tested on strings but is not yet connected to live
  python-docx/lxml nodes.
- Text-box choice/fallback handling and image OCR have not been implemented.
- No ground truth exists, so there are no accuracy, precision, recall, or F1
  values.
- No output DOCX has been created, consistent with the Phase 1 boundary.

## Recommended Phase 2 order

1. Create an isolated Python 3.13 environment, install the minimal dependencies,
   verify python-docx/spaCy compatibility, select a local English model, and
   record resolved versions/model checksum.
2. Implement read-only story/container extraction with stable IDs and exact run
   maps for body, tables, headers, footers, hyperlinks, and audited text boxes;
   add extraction regression tests against small synthetic DOCX fixtures.
3. Define the JSONL ground-truth schema and manually annotate representative
   samples before detector tuning to reduce evaluation bias.
4. Implement and exhaustively test structured recognizers in this order: email,
   IP, SSN, Luhn-validated credit card, then context-safe Indian/international
   phone. Add the specified finance/identifier/date negative cases immediately.
5. Implement contextual DOB rules, proving ordinary corporate dates remain
   untouched.
6. Add local spaCy PERSON/ORG candidates, address/postal rules, and prospectus
   context features for PERSON, COMPANY, and ADDRESS. Record evidence and
   calibrate confidence on the held-out annotations.
7. Exercise and tune overlap resolution using adversarial nested/adjacent spans;
   freeze thresholds from development samples rather than the final sample.
8. Add type-specific deterministic replacement factories and identity linking
   for coherent person/email and repeated-entity mappings.
9. Connect resolved spans to live OOXML replacement, save to a new DOCX, reopen
   it, and verify formatting/story coverage with fragmented-run/table/header/
   footer/text-box fixtures.
10. Implement the post-save leak scan and a package-level audit for residual
    text, relationships, metadata, and image-review status.
11. Redact the supplied prospectus only after the above tests pass; manually
    inspect representative rendered pages without altering the source.
12. Run exact and relaxed evaluation, report per-type/micro/macro results and a
    precisely defined accuracy, analyze errors, and finalize the short README
    and evaluation report without overstating coverage.
