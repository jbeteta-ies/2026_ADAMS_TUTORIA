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

All work must be performed through GitHub Issues and Pull Requests.

Agents must not implement untracked work unless explicitly instructed.

Every non-trivial change must:
1. Be linked to a GitHub Issue.
2. Use a dedicated branch.
3. Include validation.
4. Produce a validation report.
5. Open or update a Pull Request.
6. Stop for human review before merge.

Human approval is mandatory before merging Pull Requests.

---

## Git Workflow

### Before starting an Issue

The agent must:

1. Check the current Git status.
2. Ensure the working tree is clean.
3. Ensure the local `main` branch is synchronized with `origin/main`.
4. Read the complete GitHub Issue.
5. Identify:
   - scope
   - acceptance criteria
   - dependencies
   - risks
6. Do not start implementation if required dependencies are unresolved.

### Branch naming

Create one branch per Issue.

Format:

`issue/<issue-number>-<short-slug>`

Example:

`issue/12-import-students`

Do not reuse branches between unrelated Issues.

---

## Implementation Rules

The implementation agent must:

1. Work only within the scope of the assigned Issue.
2. Avoid unrelated refactors.
3. Prefer small, understandable changes.
4. Add or update tests when appropriate.
5. Update relevant documentation.
6. Preserve backward compatibility unless the Issue explicitly requires otherwise.
7. Never commit:
   - credentials
   - API keys
   - ADAMS session data
   - real student reports
   - personal student data
   - local SQLite databases containing real student data

If examples or fixtures require student data, use synthetic or anonymized data.

---

## Validation Requirements

Every Issue must be validated before a Pull Request is marked ready for review.

Validation must include all applicable checks defined by the project, including eventually:

- Unit tests
- Integration tests
- Linting
- Formatting checks
- Static typing
- Application startup checks
- Issue-specific acceptance tests

If a required validation fails, the Pull Request must not be marked ready for human review.

The agent must fix the problem and rerun validation.

---

## Validation Report

Before requesting human review, produce a validation report.

The report must contain:

### Issue
Issue number and title.

### Implementation Summary
Brief description of what was implemented.

### Files Changed
List of relevant files created, modified, or deleted.

### Acceptance Criteria
Each acceptance criterion must be explicitly marked:

- PASS
- FAIL
- NOT TESTED

### Validation Executed
For every check include:
- command or procedure
- result
- relevant notes

Example:

- `pytest`: PASS
- `ruff check .`: PASS
- `mypy src`: PASS
- application startup: PASS

### Risks and Limitations
Known limitations, technical debt, edge cases, or assumptions.

### Out-of-Scope Changes
List any changes made outside the Issue scope.

Expected value normally:

`None`

### Final Status

Only one of:

- `READY FOR HUMAN REVIEW`
- `NOT READY`

A Pull Request must never be presented as complete without this report.

---

## Pull Request Workflow

When implementation and validation are complete:

1. Check Git status.
2. Commit changes using a clear commit message.
3. Push the Issue branch.
4. Open a Pull Request against `main`.
5. Link the corresponding Issue.
6. Include the validation report in the Pull Request.
7. Mark the Pull Request as ready for review only if all mandatory checks pass.
8. Stop.

Do not merge the Pull Request automatically.

Do not close the Issue automatically before human approval.

---

## Human Review Gate

Human review is mandatory.

The project owner and supervising ChatGPT instance will review:
- implementation
- acceptance criteria
- validation report
- architecture
- maintainability
- possible regressions

Possible outcomes:

### Approved
The agent may be instructed to:
- merge the Pull Request
- confirm Issue closure
- delete the remote Issue branch
- delete the local Issue branch
- return to updated `main`

### Changes requested
The agent must:
1. Apply requested changes on the same Issue branch.
2. Re-run all relevant validations.
3. Produce an updated validation report.
4. Update the existing Pull Request.
5. Stop again for human review.

---

## Post-Merge Cleanup

After explicit human approval and successful merge:

1. Confirm the Pull Request is merged.
2. Confirm the Issue is closed.
3. Delete the remote Issue branch.
4. Delete the local Issue branch.
5. Checkout `main`.
6. Pull the latest `origin/main`.
7. Confirm the working tree is clean.

---

## Milestones

GitHub Milestones group related Issues.

Do not create one branch per Milestone.

Each Issue must keep its own branch and Pull Request.

A Milestone may only be considered complete when:
1. All required Issues are closed.
2. All corresponding Pull Requests are merged.
3. Any milestone-level integration validation has passed.
4. Human review approves milestone completion.

---

## Agent Roles

The project may use specialized OpenCode agents.

Suggested roles:

### Implementer
Primary model: Nemotron Ultra

Responsibilities:
- analyze Issues
- design implementation
- write code
- add tests
- update documentation

### Validator
Primary model: Muse

Responsibilities:
- independently validate implementation
- run tests and checks
- verify acceptance criteria
- identify regressions or missing cases
- produce validation findings

The validator should not silently fix implementation defects unless explicitly instructed.

### Reviewer
Primary model: Big Pickle

Responsibilities:
- review code quality
- review architecture
- inspect Issue scope compliance
- detect unnecessary complexity
- inspect test quality
- challenge assumptions

### GitHub Manager
Primary model: Nemotron Light

Responsibilities:
- Git status checks
- branch creation
- commits
- push
- Pull Request creation/update
- Issue linking
- post-merge branch cleanup

---

## Architecture Guidance

The application is expected to use Python.

Initial architectural direction:

- Python
- SQLite for local persistence
- Streamlit for local dashboard
- pytest for testing
- Ruff for linting and formatting
- mypy for static typing when practical

These choices are provisional until explicitly established by project Issues.

Do not introduce additional frameworks or infrastructure without a documented reason.

---

## Data Protection

This project may eventually process personal student data locally.

Mandatory rules:

- Real student data must not be committed to Git.
- Real ADAMS exports must not be committed to Git.
- Local databases containing personal data must be ignored by Git.
- Test fixtures must use synthetic data.
- Logs must not expose unnecessary personal information.
- Credentials must never be committed.
- `.gitignore` must protect local data directories and database files.

GitHub contains code and project documentation, not operational student data.

---

## Course Content Integration

Course contents may live in separate repositories.

This tutoring application must remain reusable across different ADAMS courses.

The application may reference or locally mount course-content repositories, but it must not hard-code business logic exclusively for IFCT0138 unless explicitly required.

Conceptual model:

Course
→ Edition
→ Student enrollment
→ Progress
→ Evaluations
→ Communications

---

## Current State

No application code exists yet.

Current repository contains only initial project files and this operational harness.

The first implementation Issues will establish:
- project structure
- Python version
- dependency management
- test tooling
- linting
- typing
- local data protection
- initial application architecture