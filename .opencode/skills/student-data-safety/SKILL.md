---
name: student-data-safety
description: Apply privacy and data-protection rules when designing, coding, testing, importing, logging, exporting, or documenting anything involving ADAMS students, reports, evaluations, communications, or local databases.
compatibility: opencode
metadata:
  audience: all-agents
  domain: privacy
---

# Student Data Safety

Use this skill whenever a task touches students, enrollments, progress, evaluations, tutor communications, imports, exports, logs, databases, fixtures, backups, or screenshots.

The Git repository stores code and safe documentation. It is not the operational store for real student data.

## Never commit

Never commit any of the following:

- real student names linked to course activity
- real student email addresses
- student identifiers from ADAMS
- attendance/progress reports containing personal data
- evaluation results tied to identifiable students
- tutor communications containing identifiable student information
- ADAMS credentials
- ADAMS cookies or session tokens
- API keys or secrets
- production/local SQLite databases containing real student records
- unredacted screenshots or exports containing personal data

When uncertain whether data is personal, treat it as personal.

## Repository safeguards

The project must keep operational data in ignored local locations.

Expected protected patterns should eventually include, as applicable:

- `data/raw/`
- `data/private/`
- `data/processed/`
- `*.db`
- `*.sqlite`
- `*.sqlite3`
- `.env`
- secret/config override files

Do not modify `.gitignore` protections to make operational files easier to commit.

## Test and demo data

Fixtures, examples, screenshots, and tests must use synthetic data.

Good examples:

- `Alumno 001`
- `ana.ejemplo@example.invalid`
- generated UUIDs
- invented scores/progress values

Synthetic test data must not be a lightly modified copy of real exports.

## Import design

Importers should:

1. Accept real files locally.
2. Convert them into the application's internal model.
3. Avoid copying source reports into tracked repository paths.
4. Validate expected columns and data types.
5. Fail safely on malformed input.
6. Avoid exposing full records in exception messages.
7. Record only the minimum metadata necessary for audit/import history.

## Logging

Logs should minimize personal data.

Prefer:

`Imported 42 enrollment rows; 2 rejected.`

Avoid:

`Imported Javier Pérez <real@email> with score 4.2.`

When a record must be referenced operationally, prefer an internal identifier rather than a full name/email.

## Generated communications

Personalized messages may be generated locally, but:

- they must not be committed to Git
- generated outputs containing real student data must live in ignored paths
- tests use synthetic recipients
- no agent may send messages through ADAMS unless an explicitly authorized integration exists in the future

The current expected workflow is human copy/paste into ADAMS.

## Course content

Public/course Markdown content can be version controlled when it contains no student data.

Do not mix course-content repositories with operational student datasets.

## Validation checklist

When reviewing a change that processes student information, verify:

- [ ] No real personal data is committed.
- [ ] Tests use synthetic data.
- [ ] Operational storage paths are ignored.
- [ ] Logs avoid unnecessary personal data.
- [ ] Errors do not expose full records.
- [ ] Generated personalized outputs are local/ignored.
- [ ] Credentials/session material cannot enter version control.
- [ ] Data collection/storage is limited to what the tutoring workflow needs.

Any material failure in this checklist blocks readiness for human review.
