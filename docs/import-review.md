# Import review and confirmation

`ImportReviewService` provides a read-only preview over the normalized import
contracts. A preview is held in memory and contains a `preview_id`, input
digest, database-state digest, timezone-aware creation time, and a closed
change taxonomy: `CHANGE`, `UNCHANGED`, `REJECTED`, `CONFLICT`, and `ERROR`.

Only a `ConfirmationRequest` with `mode="all"` can apply a preview. It carries
the preview id and digest, an aware timestamp, an idempotency key, and an
optional operator reference. Confirmation executes the existing student,
enrollment, progress, and evaluation services in one SQLite transaction. A
changed database state or normalized input invalidates the preview. Repeating
the same idempotency key is a no-op.

If any category fails, the whole application transaction is rolled back. An
independent second transaction reconstructs the batch, marks it `FAILED`, and
writes one global, privacy-safe `ERROR` audit row. `ConfirmationResult` exposes
`audit_persisted` unambiguously: it is true only when that second transaction
commits. The original failure remains in `error`; an audit persistence failure
remains in `audit_error`, and is never reported as persisted.

No course or edition is created by this boundary. Source files and raw rows are
not persisted, and connectors, UI, automatic confirmation, physical deletion,
and remote delivery remain out of scope.
