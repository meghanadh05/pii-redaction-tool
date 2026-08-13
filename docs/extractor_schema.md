# DOCX extractor/container-ID schema

The extractor schema is frozen at **1.0** for the Phase 2B development set.
Annotations are valid only when both this version and the source-document
SHA-256 match their manifest.

## Covered logical stories

- Body paragraphs: `body/pNNNN`
- Table-cell paragraphs, including recursively nested tables:
  `body/tNNNN/rNNNN/cNNNN/pNNNN`
- Distinct header/footer package parts:
  `header:<partname>:<kind>/pNNNN` and
  `footer:<partname>:<kind>/pNNNN`
- Text-box paragraphs nested below their containing paragraph:
  `<parent-id>/txbNNNN/pNNNN`

DrawingML `mc:Choice` and VML `mc:Fallback` text-box branches with identical
logical text are represented by one container ID. The primary branch owns the
run map and the fallback is a mirror; a rewrite is planned and validated for
both before either branch is mutated. Mismatched or structurally unusual
branches are extracted under branch-qualified IDs and marked unsafe to rewrite.

The extractor includes hyperlink runs and excludes text-box runs from their
outer paragraph. It deduplicates package-level headers and footers shared by
sections. Ordinary Phase 2A container IDs remain unchanged by schema 1.0.

## Versioning rule

Increment the schema version if traversal order, story coverage, ID grammar,
choice/fallback pairing, or logical span reconstruction changes in a way that
can alter container IDs or annotation offsets. Formatting-only rewrite changes
that leave extraction and spans unchanged do not require a new schema version.

## Known boundaries

Shape descriptions/titles and Selection Pane names are audited separately;
they are not ordinary text containers and are not automatically rewritten.
Raster images are not OCR'd. Complex Word fields and embedded objects fail
closed when a replacement would touch unsupported run XML.
