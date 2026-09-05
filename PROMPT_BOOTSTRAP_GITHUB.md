# Bootstrap GitHub planning with OpenCode

You are operating inside the `2026_ADAMS_TUTORIA` repository.

Read and obey:
- `AGENTS.md`
- `.opencode/skills/issue-workflow/SKILL.md`
- the GitHub Manager agent instructions

Your task is ONLY to create the initial GitHub Milestones and Issues defined in:
- `planning/milestones.yaml`
- `planning/issues.yaml`
- `planning/issues/*.md`

Use the authenticated GitHub CLI (`gh`) and `gh api`.
Do NOT use GitHub MCP.
Do NOT modify application code.
Do NOT create branches or Pull Requests for this planning bootstrap.
Do NOT close, merge, or delete anything.

## Required procedure

1. Run and report:
   - `git status`
   - `git branch --show-current`
   - `git remote -v`
   - `gh auth status`
   - `gh repo view`
2. Stop if the repository is not `2026_ADAMS_TUTORIA`, GitHub authentication fails, or there are unexpected uncommitted changes.
3. Read both YAML manifests completely.
4. Check existing GitHub milestones and issues first to avoid duplicates.
5. Create each missing milestone using `gh api`.
6. Create each missing issue using `gh issue create`, assigning the milestone by its exact title and using the corresponding Markdown file as the issue body.
7. Preserve the order from `planning/issues.yaml` when creating issues.
8. Do not recreate an existing milestone or issue if an exact matching title already exists; report it as skipped.
9. After creation, verify:
   - every milestone exists
   - every issue exists
   - every issue is assigned to the intended milestone
10. Produce a final bootstrap report with:
   - milestones created / skipped
   - issues created / skipped
   - any failures
   - verification result
   - `gh issue list --limit 100`
11. STOP for human review.

No other repository changes are authorized.
