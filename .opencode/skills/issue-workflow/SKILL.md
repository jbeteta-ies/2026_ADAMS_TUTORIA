---
name: issue-workflow
description: Resolve a GitHub Issue through the repository's mandatory branch, implementation, validation, Pull Request, human review, and cleanup workflow. Use this skill whenever working on or coordinating an Issue.
compatibility: opencode
metadata:
  audience: development-agents
  workflow: github
---

# Issue Workflow

Use this skill whenever an Issue is assigned, implemented, validated, reviewed, or prepared for merge.

The repository root `AGENTS.md` is authoritative. This skill operationalizes that policy.

## 1. Pre-flight

Before making changes:

1. Read `AGENTS.md`.
2. Read the entire assigned GitHub Issue.
3. Identify:
   - Issue number and title
   - scope
   - acceptance criteria
   - dependencies
   - risks
4. Check Git state.
5. Require a clean working tree.
6. Synchronize `main` with `origin/main`.
7. Do not implement while required dependencies are unresolved.

## 2. Branch

Use exactly one branch per Issue:

`issue/<issue-number>-<short-slug>`

Examples:

- `issue/3-project-bootstrap`
- `issue/12-import-students`

Never implement unrelated Issues on the same branch.

## 3. Implementation

The Implementer must:

1. Work only inside Issue scope.
2. Prefer the smallest maintainable solution.
3. Avoid unrelated refactors.
4. Add or update tests when appropriate.
5. Update documentation affected by the change.
6. Use synthetic/anonymized data in examples and fixtures.
7. Never commit secrets or operational student data.

When implementation appears complete, hand off to the Validator.

## 4. Independent validation

The Validator:

1. Reads the Issue and full diff independently.
2. Runs all applicable checks.
3. Verifies every acceptance criterion.
4. Produces the mandatory validation report using the `validation-report` skill.
5. Does not silently repair defects.

If validation returns `NOT READY`, hand control back to the Implementer.

The Implementer fixes defects on the same Issue branch and validation is repeated.

## 5. Review

After successful validation, the Reviewer inspects:

- correctness
- architecture
- maintainability
- Issue scope compliance
- test quality
- regressions
- unnecessary complexity
- data protection

A blocking reviewer finding must be resolved before the PR is presented as ready.

## 6. Pull Request

Only after implementation, validation, and review are satisfactory:

1. Check Git status.
2. Commit with a clear message.
3. Push the Issue branch.
4. Open or update a PR against `main`.
5. Link the Issue.
6. Include the validation report.
7. State clearly that human approval is required.
8. STOP.

Do not merge automatically.
Do not close the Issue automatically.

## 7. Human gate

The project owner and supervising ChatGPT review the PR and validation evidence.

Two outcomes are allowed.

### Changes requested

1. Keep the same Issue branch and PR.
2. Implement requested corrections.
3. Rerun all relevant validation.
4. Replace/update the validation report.
5. Update the PR.
6. STOP again.

### Approved

Only after explicit human approval may the GitHub Manager merge or perform post-merge cleanup.

## 8. Post-merge cleanup

After confirmed merge:

1. Confirm PR merged.
2. Confirm Issue closed.
3. Delete remote Issue branch.
4. Delete local Issue branch.
5. Checkout `main`.
6. Pull latest `origin/main`.
7. Confirm clean working tree.

## 9. Milestones

Milestones group Issues; they do not receive shared feature branches.

A milestone is complete only when:

- all required Issues are closed
- all PRs are merged
- milestone-level integration validation passes where applicable
- humans approve completion
