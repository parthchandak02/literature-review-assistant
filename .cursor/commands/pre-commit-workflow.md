# Pre-Commit Workflow

Prepare and commit all pending changes safely. Scan for secrets, stage clean files, and produce a conventional commit.

## Steps

1. **Audit working tree** -- Run `git status` and list every modified, added, and deleted file. Summarize what changed at a high level.

2. **Security scan** -- Inspect staged and unstaged diffs for forbidden content:
   - `.env` files or any file containing `API_KEY=`, `SECRET=`, `PASSWORD=`, `TOKEN=`, bearer tokens, or private keys
   - Any file under `runs/**` (runtime artifacts) or `*.db` files (SQLite databases)
   - Hard-coded credentials or connection strings
   - If any forbidden item is found, stop immediately and tell the user what was found. Do NOT proceed to staging.

3. **Verify project rules** -- Confirm the commit obeys `.cursor/rules/core/project-overview-always.mdc`:
   - No `.env`, `runs/**`, or run-specific generated artifacts will be staged
   - All new phase-boundary functions use Pydantic models (not plain dicts)

4. **Stage safe files** -- Add all files that passed the security scan using `git add`. List exactly which files are being staged.

5. **Write the commit message** -- Follow Conventional Commits format:
   - `feat:` for new features or capabilities
   - `fix:` for bug fixes
   - `refactor:` for restructuring without behavior change
   - `chore:` for tooling, config, or dependency updates
   - Use present tense, imperative mood, max 72 chars on the subject line
   - Add a body paragraph if the change touches more than 3 files, explaining the "why"

6. **Commit** -- Run `git commit -m "..."` using a HEREDOC to preserve formatting. Show the full commit message to the user before executing.

7. **Report** -- After committing, run `git log --oneline -5` and show the result so the user can confirm the commit landed correctly.

## Safety Rules

- NEVER stage `.env`, `runs/**`, `*.db`, or files matching `.gitignore`
- NEVER use `--no-verify` or skip hooks
- NEVER force-push to main/master
- If unsure whether a file is safe to commit, ask the user before staging it
- If a pre-commit hook rejects the commit, fix the issue and create a NEW commit -- never amend a rejected commit
