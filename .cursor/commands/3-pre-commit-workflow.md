# Pre-Commit Workflow

Prepare and commit all pending changes safely. Scan for secrets, stage clean files, and produce a conventional commit.

## Steps

1. **Audit working tree** -- Run `git status` and list every modified, added, and deleted file. Summarize what changed at a high level (which areas of the codebase are affected, what the nature of the changes is).

2. **Security scan** -- Inspect staged and unstaged diffs for forbidden content. Stop immediately and report to the user if any of the following are found -- do NOT stage or commit:
   - Environment files (`.env`, `.env.*`) or any file containing patterns like `API_KEY=`, `SECRET=`, `PASSWORD=`, `TOKEN=`, bearer tokens, or private keys
   - Runtime artifact directories (e.g. `runs/`, `outputs/`, generated data folders)
   - Database files (`*.db`, `*.sqlite`)
   - Files already listed in `.gitignore` that are somehow staged

3. **Verify project rules** -- Before staging anything, check the always-on rules in `.cursor/rules/core/` to confirm the changes comply with project constraints (e.g. no untyped dicts at phase boundaries, no LLM-computed statistics, all I/O is async). Flag any violation and ask the user how to proceed.

4. **Stage safe files** -- Add all files that passed the security scan. List exactly which files are being staged and which are being deliberately excluded.

5. **Write the commit message** -- Follow Conventional Commits format:
   - `feat:` for new features or capabilities
   - `fix:` for bug fixes
   - `refactor:` for restructuring without behavior change
   - `chore:` for tooling, config, or dependency updates
   - Use present tense, imperative mood, max 72 chars on the subject line
   - Add a body paragraph when the change touches more than 3 files, explaining the "why"

6. **Commit** -- Show the full commit message to the user, then run `git commit` using a HEREDOC to preserve formatting.

7. **Confirm** -- Run `git log --oneline -5` and show the result so the user can confirm the commit landed correctly.

## Safety Rules

- NEVER stage environment files, runtime artifacts, database files, or anything in `.gitignore`
- NEVER use `--no-verify` or skip pre-commit hooks
- NEVER force-push to main/master
- If unsure whether a file is safe to commit, ask the user before staging it
- If a pre-commit hook rejects the commit, fix the underlying issue and create a NEW commit -- never amend a rejected commit
- If major deletions or structural changes are detected, pause and confirm with the user before proceeding
