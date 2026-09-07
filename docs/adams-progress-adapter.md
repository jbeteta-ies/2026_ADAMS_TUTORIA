# Provisional ADAMS progress adapter

`adams_tutoria.adapters.adams.progress` is the source-specific boundary after
the generic `TabularRow` reader and before
`ImportResult[ImportCandidate]`. It does not create a domain progress object,
match or reconcile identities, write persistence, or log raw rows.

`AdamsProgressMapping` is immutable and caller-provided. It has no defaults for
source columns because the actual ADAMS report has not been inspected. The
mapping is the only place where a future localized report-header adaptation
belongs.

The adapter emits conservative student, edition, and enrollment evidence using
the existing import contract. A row can be identified by an enrollment
reference, or by both student and edition evidence. Course evidence alone does
not identify an edition. Progress values are preserved as normalized scalar
text; the adapter deliberately does not assume a 0–100 or 0–1 scale, range,
rounding, cumulative meaning, or semantic label. An optional timestamp accepts
only an ISO-8601 string and is stored in canonical ISO text form.

## Facts still unknown

- The real report name, file format, sheet, delimiter, encoding, and headers.
- Whether progress is a scalar, status, percentage, fraction, count, or another
  measure, and what its units or range mean.
- Whether values are current snapshots, event records, or cumulative measures.
- Which field identifies a student, enrollment, edition, or course, and whether
  identifiers are stable.
- Whether a timestamp exists, its timezone policy, and its actual format.
- Whether reports contain blank, formula, sentinel, localized-number, or other
  source-specific values.

When an approved anonymized report is available, update only this mapping and
adapter's narrowly scoped conversion logic, together with synthetic tests and
this documentation. Keep the generic reader, import contract, domain,
persistence, and application services source-independent.
