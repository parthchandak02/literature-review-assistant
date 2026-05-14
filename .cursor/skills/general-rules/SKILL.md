---
name: general-rules
description: Canonical cross-cutting workflow for session bootstrap, commit/push safety, documentation discipline, scripting, and Python environment standards. Use for most implementation tasks unless a domain-specific skill owns the workflow.
---

# General Project Rules

This is the canonical process skill for general execution in this repository.

## Workflow ownership

- Owns: session orientation, commit/push hygiene, broad engineering defaults.
- Does not own: hook installation (`setup-pre-commit`), skill-authoring internals (`write-a-skill`), source-backed external research (`research`).

## Session bootstrap workflow (canonical)

At the start of planning/editing work:

1. Read `AGENTS.md` and `.cursor/docs/INDEX.md`.
2. Read task-routed docs from `.cursor/docs/INDEX.md` only.
3. Review recent git context (`git log`, `git status`) before edits.
4. Build a quick zoom-out map: lifecycle stage, entrypoints, typed boundaries, blast radius.
5. For code-changing sessions, run task-appropriate checks before claiming completion.

When docs conflict with code, trust code and active rules, then note drift for follow-up.

## Git Security and Commit Practices

Use this sequence for commit/push work:

1. Audit working tree and summarize change areas.
2. Security-scan staged/unstaged content for secrets and forbidden artifacts.
3. Verify project invariants/rules still hold for touched areas.
4. Stage only safe files; explicitly list exclusions.
5. Plan commit boundaries by intent (split unrelated concerns).
6. Write strong conventional commit messages with clear "why".
7. Remind user before commit/push and get explicit confirmation.
8. Push only when explicitly requested.

Atomic commit rule:

- Group files into the smallest coherent change units where each commit can be understood and reverted independently.
- Do not mix docs/rules churn with behavioral code changes in the same commit.
- If a file contains changes from multiple concerns, split by concern before staging.

Hard exclusions from staging/commit unless user explicitly requests otherwise:

- `.env` / secrets
- `runs/**` or generated runtime artifacts
- runtime DB files (`*.db`, `*.sqlite`)
- ignored files that slipped into staging

## Documentation Standards

Keep documentation minimal and focused on getting started. Prioritize "How to use" in README.md.

- Only create additional `.md` files when explicitly requested
- Keep documentation short, utilitarian, no fluff
- For multi-step work, prefer the built-in todo/task tracking tools instead of creating tracking markdown files

## Engineering Patterns (Adapted)

Use these patterns for non-trivial implementation and debugging work.

### Diagnose Loop (Root-Cause First)

Follow a disciplined sequence:

1. Reproduce the failure with a deterministic command
2. Minimize scope to the smallest failing unit (module, prompt, API, or test)
3. Form 1-2 explicit hypotheses and rank by likelihood
4. Instrument with focused logs/assertions or DB/query checks
5. Fix at source in `src/` or `frontend/src/` (never patch `runs/` artifacts)
6. Add regression coverage and rerun the failing path

Stop and escalate when the failure cannot be reproduced deterministically or when two hypotheses fail without new evidence.

### TDD Vertical Slice

For feature work and bug fixes:

- Start with one failing test that proves user-visible behavior
- Implement the minimum code to pass
- Refactor only after green
- Repeat in thin slices across boundaries (API -> orchestration -> UI) instead of large rewrites
- Prefer replay/integration tests for pipeline behavior and unit tests for pure logic

### Zoom-Out Before Deep Edits

Before editing unfamiliar modules:

- Identify entrypoints, typed boundaries, and canonical source-of-truth tables/files
- Confirm lifecycle stage via `.cursor/docs/INDEX.md`
- Note likely blast radius (orchestration, API contract, persistence, UI)

If architecture uncertainty remains after this scan, pause and clarify design before implementation.

## Script Organization and Management

Use the `scripts` folder to automate important tasks. Identify and organize scripts into two types:

1. **Recurring Usage Scripts**: Automate frequent workflows (e.g., starting backend/frontend, deploying to Cloudflare, resets, batch jobs). Use Bash where possible for speed, but Python where needed.

2. **Temporary Testing Scripts**: Automate one-off or debugging steps (e.g., feature checks, API tests, quick data dumps). Clean up after use if no longer needed.

**Script Guidelines:**
- Name scripts clearly by purpose and type, e.g., `run-backend.sh`, `test-gtt-feature.py`, `debug-price-check.sh`
- Agents should intelligently pick the type and place new scripts in the correct location
- Prefer Bash for fast tasks; use Python for complex/testing automation
- Always document what each script does at the top (brief comment)
- Focus on keeping scripts modular, simple, and easy to run

## Python Environment Management

Use `uv` for dependency management and execution.

- Always use `uv` for package installation instead of pip (unless specified otherwise)
- Prefer `uv run ...` to execute Python commands
- Activate `.venv` only when direct interpreter workflows are explicitly needed

## Related skills

- `setup-pre-commit`: use only for hook installation/repair.
- `write-a-skill`: use only for creating or refactoring skills.
- `research`: use when external source-backed guidance is required.

## Code Quality and Linting

If the project uses ruff (check `pyproject.toml` for `[tool.ruff]`), use it to maintain code quality:

- **Before making code changes**: Run `ruff check .` to identify existing issues
- **After making code changes**: Always run `ruff check --fix .` to automatically fix fixable issues
- **For comprehensive fixes**: Use `ruff check --fix --unsafe-fixes .` to fix all auto-fixable issues including unsafe ones
- **Focus on critical errors**: Prioritize fixing E (errors) and F (code quality) rule violations first
- **Periodic checks**: Run `ruff check src/` before committing changes to ensure code quality
- **Configuration**: Ruff configuration is in `pyproject.toml` [tool.ruff] - respect existing settings

**Common ruff commands:**
- `ruff check .` - Check all files for issues
- `ruff check --fix .` - Auto-fix safe issues
- `ruff check --fix --unsafe-fixes .` - Auto-fix all fixable issues
- `ruff check src/ --select E,F` - Check only errors and code quality issues in src/
- `ruff check <file>` - Check specific file

**When to run ruff:**
- After fixing syntax errors or indentation issues
- Before committing code changes
- When encountering import or code quality errors
- Periodically during development to catch issues early

If ruff is not configured in the project, skip ruff-related steps.
