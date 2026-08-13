# Annotation conventions (fixed before annotating; derived from the assignment)

- **PERSON** — a named individual. Span covers given name through surname,
  including middle names/initials. Excludes honorifics (Mr., Dr.), roles
  ("Contact Person"), and designations.
- **EMAIL** — the full address, local-part through TLD.
- **PHONE** — the number as written, including country/STD code and any leading
  `+`. Excludes the "Telephone:" label.
- **COMPANY** — a commercial entity name including its legal suffix (Limited,
  Private Limited, LLP). Excludes regulators and government bodies (SEBI, RoC,
  RBI, development authorities, tax departments), legislation, courts, generic
  transaction roles ("Book Running Lead Managers"), and self-references
  ("our Company").
- **ADDRESS** — a postal address or a substantive line of one: a premise or
  building, a street, or a locality, with or without city/postcode. The
  prospectus splits single addresses across containers, so a fragment such as
  "10th Floor, Tower 2A & 2B" is annotated. A bare city, state, or country
  alone is NOT an address, and neither is a location named in narrative prose
  ("our plant at Supa, Ahilyanagar"). The span ends before adjacent
  `Telephone:` / `Email:` / `Website:` / `Contact Person:` fields.
- **SSN / CREDIT_CARD / IP_ADDRESS** — as literally defined.
- **DOB** — a date with explicit birth context only. Ordinary document dates,
  incorporation dates, and financial-year dates are NOT DOB.

Tie-break rules:

1. A company name serving only as a landmark inside an address (e.g. "above
   HDFC Limited") is annotated as part of the ADDRESS, not separately as
   COMPANY. Spans never overlap.
2. Business identifiers (CIN, DIN, SEBI registration, ISIN, page/ticket/order
   numbers, financial figures) are never PII.
3. A container listed in the manifest with no annotation is an explicitly
   reviewed negative.
