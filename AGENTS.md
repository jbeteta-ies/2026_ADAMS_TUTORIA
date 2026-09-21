# AGENTS.md - 2026_ADAMS_TUTORIA

## Project Purpose

This repository contains a local application to support tutoring and monitoring of ADAMS online courses.

The application will help manage:

- Courses
- Editions
- Students
- Progress reports
- Evaluation reports
- Tutor communications
- Local dashboards
- Assisted generation of personalized messages
- Course-content lookup for answering student questions

The official ADAMS platform remains the source of truth for course delivery, evaluations, and message sending.

Student credentials or ADAMS credentials must never be stored in this repository.

---

## Development Principles

All non-trivial work must be performed through GitHub Issues and Pull Requests.

Agents must not implement untracked work unless explicitly instructed.

Every non-trivial Issue must:

1. Be analyzed by the Planner.
2. Have an approved implementation plan.
3. Use a dedicated branch.
4. Include validation.
5. Produce a validation report.
6. Receive independent review.
7. Open or update a Pull Request.
8. Stop for human review before merge.

Human approval is mandatory at two points:

1. before implementation begins
2. before a Pull Request is merged

### Narrow harness-maintenance exception

The ordinary Issue workflow above remains mandatory for all application work,
documentation work, and other non-trivial changes. A narrow exception is
allowed only when an explicitly approved plan requests a correction to the
repository harness itself (for example, agent configuration or workflow
instructions) and no suitable GitHub Issue exists for that correction.

For that exception only:

- work must be performed on the specifically prepared branch
  `harness/fix-agents-models`;
- the implementer must modify only the files explicitly authorized by the
  approved plan and must preserve all pre-existing work on the branch;
- the exception does not authorize application changes, unrelated cleanup,
  branch creation, rebasing, resets, or destructive working-tree operations;
- independent Validator and Reviewer gates remain required;
- a Pull Request against `main` and explicit human approval remain required
  before merge; and
- no agent may commit, push, open or update a Pull Request, merge, or clean up
  the branch unless that action is separately authorized by the applicable
  workflow gate.

This exception does not waive validation, review, Pull Request, human-approval,
or merge protections, and it must not be used to bypass the normal Issue
workflow when an Issue exists or when the change is outside harness
maintenance.

---

# Mandatory Planning Gate

The Planner is the normal entry point for GitHub Issue work.

No non-trivial Issue may begin implementation before a plan has been approved.

Before any Issue branch is created or any application code is modified:

1. The Planner reads:
   - this `AGENTS.md`
   - the complete GitHub Issue
   - relevant Skills
   - relevant repository context
2. The Planner produces a complete implementation plan.
3. The plan must include:
   - objective
   - scope
   - out-of-scope work
   - technical decisions
   - expected files
   - implementation steps
   - validation strategy
   - risks and assumptions
   - dependencies
   - agent delegation
4. The plan must end with:

   `WAITING FOR PLAN APPROVAL`

5. The Planner must stop.
6. No branch creation, implementation, commit, push, or Pull Request work may begin until explicit human approval is given.

If humans request changes to the plan:

1. The Planner revises the complete plan.
2. The revised plan again ends with:

   `WAITING FOR PLAN APPROVAL`

3. The Planner stops again.

If implementation later requires a material deviation from the approved plan, work must stop and the Planner must request approval for a revised plan.

Examples of material changes:

- new framework
- new persistent dependency
- architectural change
- significant scope expansion
- new data-storage mechanism
- major new files not contemplated by the plan
- acceptance criteria cannot be met using the approved approach

Minor implementation details that do not alter architecture or scope do not require replanning.

---

# Normal Issue Workflow

The standard workflow is:

Issue
→ Planner analysis
→ Implementation Plan
→ Human plan approval
→ GitHub Manager
→ Implementer
→ Validator
→ Reviewer
→ GitHub Manager
→ Pull Request
→ Human PR approval
→ Merge
→ Cleanup

The Planner remains responsible for coordination throughout the workflow.

The approved implementation plan and the Validator's final validation report
are mandatory workflow artifacts. They must exist and be consulted as part of
the workflow, but they do not require separate versioned files when the
approved plan limits the change to `AGENTS.md`; in that case, they may remain
in the workflow record and Pull Request evidence rather than being added to
the repository.

---

## Git Workflow

### Before starting an Issue

After plan approval, the GitHub Manager must:

1. Read this `AGENTS.md`.
2. Check:
   - `git status`
   - current branch
   - configured remotes
   - `gh auth status`
   - repository accessibility
3. Ensure the working tree is clean.
4. Checkout `main`.
5. Synchronize local `main` with `origin/main`.
6. Read the complete assigned GitHub Issue.
7. Confirm:
   - scope
   - acceptance criteria
   - dependencies
   - milestone
8. Create the Issue branch.

Implementation must not start if required dependencies are unresolved.

### Branch naming

Create one branch per Issue.

Format:

`issue/<issue-number>-<short-slug>`

Example:

`issue/12-import-students`

Do not reuse branches between unrelated Issues.

Do not create one branch per Milestone.

---

## Implementation Rules

The Implementer must:

1. Read:
   - `AGENTS.md`
   - the approved Planner plan
   - the assigned Issue
2. Work only within the approved Issue scope.
3. Follow the technical decisions established by the approved plan.
4. Avoid unrelated refactors.
5. Prefer small, understandable changes.
6. Add or update tests when appropriate.
7. Update relevant documentation.
8. Preserve backward compatibility unless explicitly required otherwise.
9. Escalate material deviations back to the Planner.

The Implementer must never commit:

- credentials
- API keys
- ADAMS session data
- real student reports
- personal student data
- operational databases containing real student data

If examples or fixtures require student data, use synthetic or anonymized data.

---

## Validation Requirements

Every Issue must be independently validated before a Pull Request is presented for human review.

The Validator must:

1. Read:
   - `AGENTS.md`
   - the Issue
   - the approved plan
   - the implementation diff
2. Verify every acceptance criterion independently.
3. Run all applicable project checks.

Validation may include:

- Unit tests
- Integration tests
- Linting
- Formatting checks
- Static typing
- Application startup checks
- Database checks
- Issue-specific acceptance tests
- Regression checks
- Privacy/data-protection checks

The Validator must not silently repair defects unless explicitly instructed to change roles.

If a required validation fails:

- final validation status must be `NOT READY`
- the Planner coordinates a return to the Implementer
- corrections remain on the same Issue branch
- validation must be repeated

---

# Validation Report

Before a Pull Request can be presented for human review, a complete validation report is mandatory.

The report must contain:

## Issue

Issue number and title.

## Implementation Summary

Brief factual description of what was implemented.

## Files Changed

Relevant files created, modified, or deleted.

## Acceptance Criteria

Every acceptance criterion must be marked as:

- PASS
- FAIL
- NOT TESTED

No acceptance criterion may be omitted.

## Validation Executed

For every check include:

- command or procedure
- result
- relevant notes

Example:

- `pytest`: PASS
- `ruff check .`: PASS
- `mypy src`: PASS
- application startup: PASS

## Risks and Limitations

Known:

- limitations
- assumptions
- edge cases
- technical debt
- compatibility concerns

## Out-of-Scope Changes

Expected value normally:

`None`

## Final Status

Only one of:

- `READY FOR HUMAN REVIEW`
- `NOT READY`

A Pull Request must never be presented as complete without this report.

Validation status never authorizes merge.

---

## Reviewer Requirements

After successful validation, the Reviewer must independently assess:

- correctness
- architecture
- maintainability
- simplicity
- Issue scope compliance
- approved-plan compliance
- test quality
- regressions
- unnecessary abstractions
- error handling
- security
- privacy/data protection
- documentation quality

The Reviewer must challenge assumptions made by the Implementer.

Reviewer outcome must be one of:

- `APPROVE FOR HUMAN REVIEW`
- `REQUEST CHANGES`

Blocking Reviewer findings must be resolved before the Pull Request is presented for human review.

If changes are required:

1. The Planner coordinates corrections.
2. The Implementer modifies the same Issue branch.
3. Relevant validations run again.
4. A new validation report is produced.
5. Reviewer rechecks the solution where appropriate.

---

## Pull Request Workflow

Only after:

- implementation is complete
- validation status is `READY FOR HUMAN REVIEW`
- Reviewer returns `APPROVE FOR HUMAN REVIEW`

may the GitHub Manager prepare the Pull Request.

The GitHub Manager must:

1. Check Git status.
2. Inspect changes.
3. Confirm no sensitive data is staged.
4. Commit with a clear commit message.
5. Push the Issue branch.
6. Open or update a Pull Request against `main`.
7. Link the corresponding Issue.
8. Include:
   - implementation summary
   - validation report
   - any relevant reviewer notes
   - unequivocal evidence of the approved plan, the validation result, the
     Reviewer result, and the exact scope of the change
9. Verify Pull Request state using `gh`.
10. Stop.

The Pull Request description is the required durable summary of that evidence:
it must identify the approved plan, state the Validator's final result, state
the Reviewer's result, and explicitly identify the files and scope changed.
For the narrow harness-maintenance exception, it must also make clear that
the approved plan authorized the harness-only scope and that no other files
were changed. These requirements apply even when the plan does not require
the plan or validation report to be committed as separate files.

Do not merge automatically.

Do not close the Issue before the authorized workflow permits it.

For the narrow harness-maintenance exception, the corresponding Pull Request
must identify the approved harness plan, the preserved branch
`harness/fix-agents-models`, the Validator result, and the Reviewer result.
The same human Pull Request approval and merge gates apply; the exception does
not permit direct integration into `main`.

---

# Human Pull Request Gate

Human review is mandatory.

The project owner and supervising ChatGPT instance review:

- implementation
- approved-plan compliance
- acceptance criteria
- validation report
- Reviewer findings
- architecture
- maintainability
- regressions
- privacy implications

Possible outcomes:

## Approved

The GitHub Manager may be instructed to:

- merge the Pull Request
- confirm Issue closure
- delete branches
- synchronize `main`

## Changes requested

The Planner coordinates:

1. corrections on the same Issue branch
2. revalidation
3. updated validation report
4. updated review where appropriate
5. Pull Request update
6. another human review stop

---

## Merge Rules

Merge is forbidden without explicit human approval.

Before merge, the GitHub Manager must:

1. Confirm explicit approval.
2. Verify PR state with `gh`.
3. Confirm mandatory checks remain successful.
4. Confirm no new blocking changes have appeared.
5. Respect repository protection rules.

Do not force merge around failing checks.

Do not bypass protections.

---

## Post-Merge Cleanup

After explicit approval and successful merge:

1. Confirm the Pull Request is merged.
2. Confirm the Issue is closed when expected.
3. Delete the remote Issue branch.
4. Checkout `main`.
5. Pull latest `origin/main`.
6. Delete the local Issue branch.
7. Run:
   - `git status`
   - `git branch --show-current`
8. Confirm:
   - current branch is `main`
   - local `main` is synchronized
   - working tree is clean

Do not delete branches containing unmerged work.

---

## Milestones

GitHub Milestones group related Issues.

Do not create one development branch per Milestone.

Each Issue retains:

- its own plan
- its own branch
- its own implementation
- its own validation
- its own review
- its own Pull Request
- its own human gates

A Milestone may only be considered complete when:

1. All required Issues are closed.
2. All required Pull Requests are merged.
3. Any milestone-level integration validation has passed.
4. Human review approves milestone completion.

---

# Agent Roles

## Planner

Primary model: Nemotron Ultra

Responsibilities:

- primary interaction point
- analyze Issues
- produce implementation plans
- obtain human plan approval
- coordinate specialized agents
- enforce scope
- handle material replanning
- coordinate validation/review failure loops
- stop at human gates

The Planner does not implement application code.

---

## GitHub Manager

Primary model: Nemotron Light

Responsibilities:

- Git status checks
- synchronization
- branch creation
- commits
- push
- Pull Request creation/update
- Issue linking
- Pull Request verification
- merge after explicit approval
- post-merge branch cleanup

GitHub operations use:

- `git`
- authenticated `gh` CLI

GitHub MCP is not used.

The GitHub Manager must not create an Issue branch before Planner approval.

---

## Implementer

Primary model: Nemotron Ultra

Responsibilities:

- follow the approved plan
- implement Issue scope
- write code
- add tests
- update required documentation
- report deviations

The Implementer must not make material architectural decisions outside the approved plan.

---

## Validator

Primary model: `openai/gpt-5.6-luna`

Responsibilities:

- independently validate implementation
- run checks
- verify acceptance criteria
- detect regressions
- verify privacy/data protection
- produce validation findings
- produce mandatory validation report

The Validator must not silently repair defects.

---

## Reviewer

Primary model: `github-copilot/mai-code-1.1-flash`

Responsibilities:

- independent code review
- architecture review
- scope review
- approved-plan compliance
- test-quality review
- maintainability review
- complexity review
- privacy/security review

The Reviewer does not implement fixes.

---

# Architecture Guidance

The application is expected to use Python.

Initial architectural direction:

- Python
- isolated local virtual environment
- SQLite for local persistence
- Streamlit for local dashboard
- pytest for testing
- Ruff for linting and formatting
- mypy for static typing when practical

These choices remain provisional until established by approved Issues.

Do not introduce additional frameworks or infrastructure without a documented reason and Planner approval.

---

# Dependency and Environment Guidance

Project dependencies must not be installed globally.

Use an isolated local virtual environment for project dependencies.

The expected initial direction is:

- Python 3.13
- `uv`
- project-local `.venv`

These decisions must still be established formally through the corresponding Issue and approved plan.

The local virtual environment must not be committed to Git.

---

# Data Protection

This project may eventually process personal student data locally.

Mandatory rules:

- Real student data must not be committed to Git.
- Real ADAMS exports must not be committed to Git.
- Local databases containing personal data must be ignored by Git.
- Test fixtures must use synthetic data.
- Logs must not expose unnecessary personal information.
- Credentials must never be committed.
- Generated communications containing real student information must remain in ignored local storage.
- `.gitignore` must protect operational data directories and database files.

When work touches:

- students
- enrollments
- progress
- evaluations
- communications
- imports
- exports
- logs
- databases

the `student-data-safety` Skill must be applied.

GitHub contains code and safe project documentation, not operational student data.

---

# Course Content Integration

Course contents may live in separate repositories.

This tutoring application must remain reusable across different ADAMS courses.

The application may reference or locally mount course-content repositories, but it must not hard-code business logic exclusively for IFCT0138 unless explicitly required.

Conceptual model:

Course
→ Edition
→ Student Enrollment
→ Progress
→ Evaluations
→ Communications

---

# Skills

Project Skills are stored under:

`.opencode/skills/`

Current expected Skills include:

- `issue-workflow`
- `validation-report`
- `student-data-safety`

Agents should load relevant Skills when the task requires them.

---

# GitHub Interface

GitHub operations use the authenticated GitHub CLI:

`gh`

Expected commands include, where applicable:

- `gh auth status`
- `gh repo view`
- `gh issue list`
- `gh issue view`
- `gh pr list`
- `gh pr create`
- `gh pr view`
- `gh pr edit`
- `gh pr comment`
- `gh pr checks`
- `gh pr merge`
- `gh api`

GitHub MCP is not part of the current project workflow.

---

# Forbidden Actions

Agents must not:

- implement non-trivial Issues without Planner approval
- create Issue branches before plan approval
- silently expand Issue scope
- bypass the Validator
- bypass the Reviewer
- skip validation reports
- merge without explicit human approval
- push directly to `main`
- use GitHub MCP
- commit credentials or secrets
- commit real student data
- commit operational ADAMS reports
- commit databases containing real student data
- invent unconfirmed ADAMS report formats as definitive
- delete unmerged branches
- force-push unless explicitly authorized
- bypass mandatory failing checks

---

# Current State

The repository currently contains:

- project documentation
- OpenCode harness
- specialized agents
- project Skills
- GitHub planning files
- Milestones and Issues already created in GitHub

No application implementation should begin until the relevant Issue passes the Planner approval gate.

The first development Issue is expected to establish:

- project structure
- Python version
- dependency management
- isolated environment
- minimal executable application
