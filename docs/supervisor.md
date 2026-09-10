# Supervisor MVP

The optional Supervisor is started as the normal OpenCode primary agent named
`supervisor`. It uses `openai/gpt-5.6-luna` through the OpenCode OpenAI OAuth
connection. No project API-key configuration is needed.

It delegates only to Planner, Implementer, Validator, Reviewer, and GitHub
Manager using native OpenCode tasks. The flow is:

`Issue → Planner → PLAN APPROVED → Implementer → Validator → Reviewer → PR APPROVED → GitHub Manager`

The Supervisor reviews plans, routes validation/review corrections, and sends
material replanning back through Planner. The exact standalone phrases
`PLAN APPROVED` and `PR APPROVED` are required. Responses such as “yes” or
“continue” are ambiguous and do not pass a gate.

The session limits are three plan iterations and three correction/review
cycles. Reaching either limit stops the Supervisor and requests human
intervention; it never advances automatically.

These are conversational gates in the Supervisor instructions, not global
OpenCode runtime enforcement. A user can still open another session and call
an existing agent or Git directly. The existing manual workflow remains
supported.
