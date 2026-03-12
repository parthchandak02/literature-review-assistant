# Pre-Commit Workflow

Prepare and commit all pending changes safely. Scan for secrets, stage clean files, and produce clear, high-signal conventional commits.

## Steps

1. **Audit working tree** -- Run `git status` and list every modified, added, and deleted file. Summarize what changed at a high level (which areas of the codebase are affected, what the nature of the changes is).

2. **Security scan** -- Inspect staged and unstaged diffs for forbidden content. Stop immediately and report to the user if any of the following are found -- do NOT stage or commit:
   - Environment files (`.env`, `.env.*`) or any file containing patterns like `API_KEY=`, `SECRET=`, `PASSWORD=`, `TOKEN=`, bearer tokens, or private keys
   - Runtime artifact directories (e.g. `runs/`, `outputs/`, generated data folders)
   - Database files (`*.db`, `*.sqlite`)
   - Files already listed in `.gitignore` that are somehow staged

3. **Verify project rules** -- Before staging anything, check the always-on rules in `.cursor/rules/core/` to confirm the changes comply with project constraints (e.g. no untyped dicts at phase boundaries, no LLM-computed statistics, all I/O is async). Flag any violation and ask the user how to proceed.

4. **Stage safe files** -- Add all files that passed the security scan. List exactly which files are being staged and which are being deliberately excluded.

5. **Plan commit boundaries first** -- Before committing, split staged files into logical groups so each commit is independently understandable:
   - Prefer multiple commits when changes span different concerns (e.g., screening logic vs docs vs frontend cleanup)
   - Keep each commit scoped to one intent and one primary "why"
   - If everything is one tiny change, a single commit is acceptable
   - List planned commit groups before running `git commit`

6. **Write commit messages** -- Follow Conventional Commits format with rich detail:
   - `feat:` for new features or capabilities
   - `fix:` for bug fixes
   - `refactor:` for restructuring without behavior change
   - `chore:` for tooling, config, or dependency updates
   - Use present tense, imperative mood, and target the subject line close to (but not over) 72 characters
   - For commits touching more than 3 files, include an in-depth body:
     - Why this change was needed
     - What behavior/risk was addressed
     - Any compatibility or migration notes
   - Prefer 2-5 concise body bullets over vague one-liners
   - Avoid generic subjects like "update files" or "misc fixes"

7. **Commit in sequence** -- For each planned commit group:
   - Stage only that group
   - Show the full commit message to the user
   - Run `git commit` using a HEREDOC to preserve formatting
   - Re-check `git status` before starting the next group

8. **Confirm** -- Run `git log --oneline -5` and show the result so the user can confirm the commit sequence landed correctly.

## Safety Rules

- NEVER stage environment files, runtime artifacts, database files, or anything in `.gitignore`
- NEVER use `--no-verify` or skip pre-commit hooks
- NEVER force-push to main/master
- If unsure whether a file is safe to commit, ask the user before staging it
- If a pre-commit hook rejects the commit, fix the underlying issue and create a NEW commit -- never amend a rejected commit
- If major deletions or structural changes are detected, pause and confirm with the user before proceeding
- If a commit message is weak, rewrite it before committing -- message quality is part of the workflow
