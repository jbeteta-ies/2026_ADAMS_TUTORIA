# Provisional ADAMS student/enrollment adapter

`adams_tutoria.adapters.adams` is the ADAMS-specific boundary after the
generic `TabularRow` reader and before the source-independent
`ImportResult[ImportCandidate]` contract. It does not import the domain model,
match or deduplicate records, write SQLite, or log raw rows.

`AdamsStudentEnrollmentMapping` is an immutable configuration. Column names
can be reused by default: there is deliberately no universal one-to-one
column invariant. This reuse policy is provisional and must be confirmed
against the first real report.

The current `full_name` handling is a provisional direct strategy: a trimmed
value is placed in `StudentEvidence.name`. It is not name parsing or identity
matching. Edition evidence requires `edition_reference` or `edition_label`;
`course_reference` alone is intentionally insufficient.

## Facts still to confirm from a real report

- Exact headers and whether headers vary by course or edition.
- Whether student, enrollment, edition, and course identifiers exist, and
  their stable types and semantics.
- Whether one identifier may safely be reused for multiple mapped fields.
- Whether names are a single full-name value or separate components.
- Which field identifies an edition rather than merely a course.
- Whether blank, numeric, date, formula, or sentinel values occur in mapped
  columns.
- Whether CSV delimiter/encoding or XLSX sheet selection needs source-specific
  configuration.

## Future adaptation process

When an approved, anonymized report example is available, first record its
confirmed structure and update only this adapter's mapping/configuration and
synthetic tests. Add narrowly scoped conversion rules only for observed safe
types. Re-run the generic reader and adapter boundary tests, then document any
new confirmed facts. Do not move ADAMS column knowledge into the domain,
contract, reader, persistence, or application services.
