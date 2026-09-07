# Provisional ADAMS evaluation adapter

`adams_tutoria.adapters.adams.evaluation` is the source-specific boundary
between the generic CSV/XLSX reader and `ImportResult[ImportCandidate]`. It
does not create `Evaluation` objects or another import record, match
identities, calculate grades or pass rules, persist data, or expose raw rows.

`AdamsEvaluationMapping` is immutable and caller-provided. The actual ADAMS
headers are intentionally unknown, so no headers are invented here. The
mapping is the only place where a future report-specific interpretation should
be configured.

Status handling is deliberately conservative. A source status must appear in
the explicit `status_mapping`; unknown statuses are rejected. Only a source
status mapped to `completed` emits `status=completed`. `completed_at`, `score`,
and `passed` are optional result values and never infer completion. Scores are
preserved as scalar text and `passed` is accepted only as an explicit boolean
value; no grade or pass calculation is performed.

Rows need conservative enrollment evidence and, when `evaluation_reference`
and/or `target_label` is configured, usable evidence in at least one of those
configured fields. Missing columns and empty values therefore cannot produce a
status-only candidate. The status column is also caller-provided and required;
the adapter does not assume a header named `status`. Score text must be
numeric, while its original decimal scale is preserved. Accepted output uses
only the shared import contract and is safe to feed from synthetic CSV/XLSX
fixtures. Operational exports must remain local and must not be copied into
the repository.
