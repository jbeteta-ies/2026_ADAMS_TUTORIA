# Internal import contract

`adams_tutoria.import_contract` is the boundary between source adapters and
the application. It uses only standard-library frozen dataclasses, enums, and
`Protocol`; it does not know about ADAMS columns or file formats.

An adapter translates its source into `ImportCandidate` values and returns an
`ImportResult`. Results can contain accepted records, privacy-safe
`RejectedRow` diagnostics, and provenance-aware non-fatal `ImportWarning`
values at the same time. Diagnostics retain only source kind/name, an
optional row number or source identifier, a code, and a safe message. They
must never retain the raw row or personal values.

## Evidence rules

- `ResolutionReference` accepts a source reference, a label, or both.
- Edition evidence is `edition_reference` **or** `edition_label`.
  `course_reference` alone never qualifies an edition.
- Enrollment evidence is `enrollment_reference`, or student evidence **and**
  edition evidence.
- Student candidates require non-empty `StudentEvidence` (a reference, name,
  or email). `PROGRESS` and `EVALUATION` candidates intentionally do not yet
  receive entity-specific evidence validation; their contract will be defined
  by a later Issue once their stable evidence fields are agreed. They still
  carry provenance and may use the general result/diagnostic rules below.

These checks are evidence checks, not matching or reconciliation. Persistence,
deduplication, fuzzy matching, and source parsing belong to later layers.

## External student identity resolution

`ExternalStudentIdentity` is the only stable student lookup key: the tuple
`source + context + source_student_id`. It is intentionally not globally unique.
`ExternalIdentityResolver` accepts an `ImportCandidate` and a read-only lookup;
it returns `existing`, `new`, `conflict`, or `rejected` outcomes without writing
SQLite or creating `Course`/`Edition` records. Names and email addresses are
descriptive evidence only and are never used for matching. Missing editions and
incomplete identities are rejected with short, non-sensitive diagnostics.

`action` and `group` are optional nullable candidate metadata. They are carried
through resolution but do not affect identity matching.

## Candidate values and warning codes

`ImportCandidate.values` is an escape hatch for normalized, application-owned
scalar values that are useful to consumers but are not part of the typed
evidence model. It is a tuple of non-blank key/value pairs. It must not contain
source column names, raw rows, credentials, or unnecessary personal data, and
consumers must not treat it as a source-specific schema. The current contract
enforces only the non-blank key/value invariant; adapters own the remaining
content boundary.

Warning `code` values remain open-ended strings because adapters can report
source- or adapter-specific non-fatal conditions without requiring a central
enum change for every new integration. Codes must still be non-blank and
stable enough for logs and tests; messages provide human-readable context.

## Import batches and provenance

`ImportBatch` records one execution using safe metadata, timezone-aware dates,
counters, and a lifecycle status. The source file and raw rows are never
persisted. Statuses are `pending`, `confirmed`, `applied`, `rejected`, and
`failed`; only pending/confirmed may advance and terminal statuses cannot
transition again. `ImportBatchChange` stores compact audit or diagnostic data
linked to a batch, without raw rows or unnecessary PII.

## Adding an adapter

Implement `ImportAdapter.adapt`. Keep source-specific columns and parsing
inside that adapter. Emit typed contract values, attach a `Provenance` to
every candidate/diagnostic, reject malformed input with a `RejectedRow`, and
return independent successes rather than failing the whole batch. Do not add
source columns, raw rows, credentials, or operational data to this module or
tracked tests. New adapters should have synthetic tests for valid rows,
 rejected rows, warnings, and partial success.

## Spreadsheet contracts

`adams_tutoria.excel_contract` defines three separate typed records:
`StudentRecord`, `ProgressRecord`, and `EvaluationRecord`. Their configurable
column objects are caller-owned mappings; the project does not assert any
official ADAMS header names. Values are normalized conservatively (whitespace,
finite numbers, and ISO-8601 timestamps), while optional fields including
`action` and `group` remain nullable. Evaluation status labels require an
explicit caller mapping. Each row retains minimal provenance and failures are
returned independently, allowing partial success. Bounded `raw_values` may
contain only a selected set of short scalar values, never a complete row.
These contracts do not create courses or editions and do not persist source
files or rows.

## Evolution application

`ProgressRecord` is normalized evidence only. `ProgressImportService` applies it
against an already existing enrollment and content node; it does not create or
infer either one. The stored node snapshots are append-only. An observation is
identified deterministically by enrollment, node, capture timestamp, and
normalized percentage, so replaying it is unchanged while a different value is
a new historical snapshot. Invalid percentages, missing timestamps, unknown
references, and cross-edition references become privacy-safe `ImportBatchChange`
diagnostics. Evaluation records use a separate table and service boundary.
