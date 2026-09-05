---
name: validation-report
description: Produce the mandatory independent validation report required before any Pull Request can be presented for human review. Use after implementing an Issue and whenever requested changes require revalidation.
compatibility: opencode
metadata:
  audience: validators-reviewers
  artifact: validation-report
---

# Validation Report

Use this skill to validate an Issue implementation and produce a standardized report.

The report must be factual and reproducible. Never convert uncertainty into PASS.

## Validation principles

1. Read `AGENTS.md`.
2. Read the complete Issue.
3. Inspect the complete diff.
4. Determine which validations are applicable.
5. Run checks rather than assuming they pass.
6. Record actual commands/procedures and results.
7. Verify every acceptance criterion separately.
8. Treat privacy/data-protection requirements as acceptance constraints when relevant.

Typical checks may include:

- unit tests
- integration tests
- lint
- formatting checks
- static typing
- application startup
- database/migration checks
- Issue-specific functional tests
- regression checks

## Status rules

Use:

- `PASS` only when verified successfully.
- `FAIL` when verified and incorrect/failing.
- `NOT TESTED` when not verified.

The final status must be `NOT READY` when:

- any mandatory acceptance criterion is FAIL
- a mandatory criterion remains NOT TESTED without justification
- a required automated check fails
- a material regression exists
- a material privacy/security risk remains unresolved

Otherwise the final status may be `READY FOR HUMAN REVIEW`.

This status never authorizes merge.

## Required report template

Produce exactly these sections.

# Validation Report

## Issue

`#<number> - <title>`

## Implementation Summary

Brief factual summary of the implementation.

## Files Changed

- `path/to/file`
- `path/to/another-file`

Include created, modified, and deleted files relevant to the Issue.

## Acceptance Criteria

For every criterion from the Issue:

- **PASS** — criterion text — evidence
- **FAIL** — criterion text — evidence
- **NOT TESTED** — criterion text — reason

Do not omit criteria.

## Validation Executed

For every validation:

### `<command or procedure>`

- Result: `PASS | FAIL | NOT TESTED`
- Notes: concise evidence, output summary, or reason.

Examples:

### `pytest`

- Result: `PASS`
- Notes: 18 tests passed.

### `ruff check .`

- Result: `PASS`
- Notes: No lint errors.

### Application startup

- Result: `PASS`
- Notes: Application started locally without startup exceptions.

## Risks and Limitations

List known:

- assumptions
- limitations
- edge cases
- technical debt
- compatibility concerns

If none are known, write:

`None identified.`

## Out-of-Scope Changes

Normally:

`None`

If any exist, list them explicitly and explain why they occurred.

## Final Status

Exactly one:

`READY FOR HUMAN REVIEW`

or

`NOT READY`

## Revalidation

When changes are requested:

1. Re-run all validations affected by the changes.
2. Re-run previously mandatory project-wide checks.
3. Update acceptance-criteria evidence.
4. Replace stale conclusions.
5. Produce a new complete report; do not merely append a patch note.
