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

## Confirmed evolution XLSX

`adams_tutoria.evolution_xlsx` parses the confirmed local report as `Usuario`
blocks, retaining column G (`Evolución`) separately from detail percentages.
Only modules 1–4 and titles using the `module + Roman numeral` convention are
eligible; activities, evaluations, presentation, summary and final-case rows
are excluded. Blocks resolve only through existing `dni/global` enrollment
identities, never by name. Preview is non-persistent; confirmed application is
transactional and stores current state in dedicated tables, leaving historical
`ContentProgressSnapshot` observations untouched. Missing later rows are kept
as the last known state. Operational files remain local and ignored.

## Confirmed contract boundaries

The authorized sample confirmed only the `Usuario` block layout, column G
(`Evolución`), the 0–100 percentage range, and the module/submodule naming
convention described above. The adapter does not assign semantics to excluded
columns, activities, evaluations, or rows outside that convention. The
`Usuario` value is an exact `dni/global` identity already attached to an
`Enrollment`; names are never used for matching.

The import is an explicitly confirmed, local operation. Preview calculates
real change, unchanged, and rejected counters without writing. Confirmation
records privacy-safe `import_batch`/`import_batch_change` metadata and applies
all state changes in one transaction. It never stores source rows or PII.
