# Supervisor MVP

The optional Supervisor is started as the normal OpenCode primary agent named
`supervisor`. It uses `openai/gpt-5.6-luna` through the OpenCode OpenAI OAuth
connection. No project API-key configuration is needed.

It delegates only to Planner, Implementer, Validator, Reviewer, and GitHub
Manager using native OpenCode tasks. The flow is:

`Issue → Planner → PLAN APPROVED → Implementer → Validator → Reviewer → GitHub Manager (PR PREPARATION) → PR APPROVED → GitHub Manager (FINAL WORKFLOW)`

The Supervisor reviews plans, routes validation/review corrections, and sends
material replanning back through Planner. The exact standalone phrases
`PLAN APPROVED` and `PR APPROVED` are required. Responses such as “yes” or
“continue” are ambiguous and do not pass a gate.

The session limits are three plan iterations and three completed corrective
review cycles. The initial Implementer → Validator → Reviewer sequence is
`REVIEW_ITERATION: 0/3`. An explicit `REQUEST CHANGES` from Validator or
Reviewer starts a corrective cycle but does not increment the counter. The
counter remains unchanged while Implementer → Validator → Reviewer is running
and increments exactly once after that complete corrective route finishes.
Replanning through Planner does not increment this counter. Reaching either
limit stops the Supervisor and requests human intervention; it never advances
automatically. Starting correction and every intermediate delegation leave
the counter unchanged. The corrective review limit is `3/3`.

Every new workflow starts with `PLAN_ITERATION: 0/3` and
`REVIEW_ITERATION: 0/3`; counters are not carried over from another workflow.
`PLAN_ITERATION` increases only when the Supervisor requests a new Planner
iteration.

There is no `GLOBAL_TRANSITION_LIMIT` or `GLOBAL_TRANSITIONS` counter. The
workflow uses only the independent `3/3` plan and corrective-review limits.

For example, a cycle that begins at `REVIEW_ITERATION: 2/3` remains at `2/3`
while its Implementer → Validator → Reviewer route is running and becomes
`3/3` only after the complete route finishes.

These are conversational gates in the Supervisor instructions, not global
OpenCode runtime enforcement. A user can still open another session and call
an existing agent or Git directly. The existing manual workflow remains
supported.

## GitHub Manager phases

The Supervisor separates GitHub Manager work into two phases.

### PR PREPARATION — before `PR APPROVED`

After Validator and Reviewer are satisfactory, the Supervisor may delegate
GitHub Manager before the second human gate. GitHub Manager commits the
validated changes, pushes the Issue branch, creates or updates the PR, includes
the final Validator report and Reviewer result, and verifies that the published
PR exactly matches the validated and reviewed state.

This phase must not merge, close the Issue, delete branches, or perform
cleanup. The Supervisor then presents the prepared PR and stops for the exact
standalone phrase `PR APPROVED`.

### FINAL WORKFLOW — after exact `PR APPROVED`

Only after receiving exactly `PR APPROVED` may the Supervisor delegate the
final workflow. GitHub Manager verifies the PR and checks, merges, confirms
Issue closure when applicable, deletes the branches, synchronizes `main`, and
performs cleanup. The pre-gate prohibition applies to these merge and cleanup
operations, not to PR PREPARATION.
