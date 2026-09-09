# Communication catalog

Issue #18 defines the initial catalog of communication purposes that later
recommendation and generation features may refer to. The catalog is deliberately
independent of ADAMS, persistence, UI, email delivery, and message generation.
It describes *what kind* of communication may be relevant; it does not decide
whether to recommend one or send it.

## Initial types

| Identifier | Purpose | Conditions |
| --- | --- | --- |
| `invitation_to_start` | Invite an enrolled student to begin the course. | The student is enrolled and has not started the course. |
| `inactivity_reminder` | Remind a student who has stopped progressing to resume study. | The student has started, and no qualifying activity exists in the configured inactivity window. |
| `pending_evaluation_reminder` | Remind a student about an evaluation that remains pending. | A required evaluation is pending and available to the student. |
| `passed_evaluation_congratulation` | Congratulate a student after a passed evaluation. | A completed evaluation has an explicit passing result. |
| `insufficient_result_encouragement` | Encourage a student after an insufficient evaluation result. | A completed evaluation has an explicit insufficient result. |
| `completion_congratulation` | Congratulate a student after completing the course. | The course completion condition has been established. |

Identifiers are stable technical keys. They are not translated display labels,
and callers should persist or exchange them only when a later Issue explicitly
introduces such behavior.

## Immutability and extension

`COMMUNICATION_CATALOG` is an ordered, immutable catalog of six
`CommunicationType` values. Each value contains an identifier, purpose,
conditions, and tone metadata. The default tone is `neutral`.

Tone metadata can be configured with `CommunicationCatalog.with_tones(...)`.
That operation returns a new catalog and cannot alter purpose or condition
metadata. It does not generate text or select a tone based on student data.

Additional types can be added by supplying another `CommunicationType` to a
new `CommunicationCatalog`. Definitions remain data-driven: consuming code
looks up identifiers and must not need a central `if`/`elif` rule set.

## Explicit boundaries

- No automatic sending or ADAMS connector is provided.
- No email integration is provided.
- No message templates or personalized text are provided.
- No persistence or UI integration is provided.
- Conditions are descriptive metadata; evaluating them belongs to future Issues.
