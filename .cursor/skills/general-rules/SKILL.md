---
name: general-rules
description: Canonical cross-cutting workflow for session bootstrap, commit/push safety, documentation discipline, scripting, and Python environment standards. Use for most implementation tasks unless a domain-specific skill owns the workflow.
---

# General Project Rules

This is the canonical process skill for general execution in this repository.

## Workflow ownership

- Owns: session orientation, commit/push hygiene, pre-commit hook repair, broad engineering defaults.
- Does not own: skill-authoring internals (`write-a-skill`), source-backed external research (`research`).
- Commit/push remains here (not a standalone `commit-and-push` skill).

## Session bootstrap workflow (canonical)

At the start of planning/editing work:

1. Read `AGENTS.md` and `.cursor/docs/INDEX.md`.
2. Read task-routed docs from `.cursor/docs/INDEX.md` only.
3. Review recent git context (`git log`, `git status`) before edits.
4. Build a quick zoom-out map: lifecycle stage, entrypoints, typed boundaries, blast radius.
5. For code-changing sessions, run task-appropriate checks before claiming completion.

When docs conflict with code, trust code and active rules, then note drift for follow-up.

## Git Security and Commit Practices

Canonical landing workflow for this repo. Push is never automatic: only push when the user explicitly asks (or says "commit and push" / "land this"). If push intent is ambiguous, ask once. Remind the user and get explicit confirmation before commit or push.

### Sequence overview

```
Phase 0  Probe          git status, branch, diff (scope + intent)
Phase 1  Doc sync       update docs the diff makes stale
Phase 2  Quality gate   run project verify/test/lint
Phase 3  Commit         cluster staging, one concern per commit
Phase 4  Push           only when the user asked
Phase 5  Report         output contract + optional next steps
```

Use this sequence for commit/push work:

1. Audit working tree and summarize change areas (Phase 0).
2. Security-scan staged/unstaged content for secrets and forbidden artifacts.
3. Sync docs the diff makes stale when contracts moved (Phase 1).
4. Run the quality gate and verify project invariants still hold (Phase 2).
5. Stage only safe files; explicitly list exclusions.
6. Plan commit boundaries by intent; split unrelated concerns (Phase 3).
7. Write strong conventional commit messages with clear "why" (HEREDOC).
8. Remind user before commit/push and get explicit confirmation.
9. Push only when explicitly requested (Phase 4).
10. Report the output contract (Phase 5).

### Phase 0: Probe

From the repo root:

```bash
git status --short
git branch -vv
git diff --stat
```

Confirm: not detached HEAD, a tracking remote exists if pushing is in scope, and the changes match what the user described. If work spans sessions, read any handoff notes the project already keeps for that purpose.

### Phase 1: Doc sync

Before the first commit, check whether the diff makes project documentation stale. Prefer existing project docs over inventing new ones.

When the diff touches contracts (architecture, phases/checkpoints, public API, persistence/schema, frontend phase alignment, or `.cursor/` agent docs):

1. Update the matching docs under `.cursor/docs/` (route via `.cursor/docs/INDEX.md`).
2. Run the **Before you commit** section in `.cursor/docs/IMPLEMENTATION_STATUS.md` (docs-to-code parity + verification gates).
3. Keep `AGENTS.md` and other agent-facing entrypoints consistent if they reference changed paths or workflows.

Common candidates: `AGENTS.md`, `README.md`, `.cursor/docs/*`, `.cursor/rules/*`, skill ownership notes under `.cursor/skills/README.md`.

If nothing needs updating, say so and move on. Do not invent a documentation convention the project does not already have.

### Phase 2: Quality gate

Run the project's existing gate; do not invent one.

1. Prefer `make release-check` when present and the change is release-bound.
2. Otherwise prefer `make local-ci` when present.
3. If neither Makefile target applies or exists, fall back as applicable:
   - Backend: `ruff check` / `uv run pytest` on touched areas
   - Frontend: `pnpm typecheck` (and lint/build when the change requires it)

Fix failures before committing, or get explicit user sign-off to commit anyway.

#### Hook repair (when pre-commit is missing or broken)

Use this only when hooks fail, are not installed, or the user asks to set them up during `/commit`.

Default to Python `pre-commit` for this repo. Use frontend local hooks only when JS/TS files are in scope. Do not replace with Husky or a generic Node/Swift stack detector unless the user explicitly asks.

1. Inspect existing `.pre-commit-config.yaml`, Ruff config, frontend lint scripts, and CI. Extend what exists; preserve hook IDs, `entry` commands, and `files` globs unless redesign is requested.
2. Install tooling: `uv add --dev pre-commit` (or `uv tool install pre-commit` when deps must not change).
3. Ensure `.pre-commit-config.yaml` has fast deterministic checks (whitespace/EOF, YAML/TOML, Ruff). If the Ruff hook has no pinned `rev`, look up the current stable `rev` at install time; keep an existing pin unless upgrading.
4. Optional frontend local hooks: `pnpm -C frontend lint`, `pnpm -C frontend typecheck` (scoped; skip when frontend untouched).
5. Install and verify:

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

Fix root cause before continuing the commit sequence.

### Phase 3: Clustered commits

Atomic commit rule:

- Group files into the smallest coherent change units where each commit can be understood and reverted independently.
- Do not mix docs/rules churn with behavioral code changes in the same commit.
- If a file contains changes from multiple concerns, split by concern before staging.

Recommended cluster order for larger passes (roughly 2-8 commits when needed):

1. Docs / rules / config that other commits depend on being read correctly.
2. Backend / core logic (`src/`).
3. Shared libraries or primitives.
4. Feature-level or UI code (`frontend/src/`).
5. Scripts, tooling, CI.

Stage explicitly (`git add -- <paths>`) rather than `git add -A` when the working tree has unrelated dirty files. Match existing commit message style from `git log`. Write the "why" in the body when it is not obvious from the subject.

Hard exclusions from staging/commit unless user explicitly requests otherwise:

- secrets / credential files
- `runs/**` or generated runtime artifacts
- runtime DB files (`*.db`, `*.sqlite`)
- ignored files that slipped into staging

Safety rules (hard):

- Only commit when the user asked.
- Never run `git config`.
- Never use `--force`, `--force-with-lease`, `--no-verify`, or history rewrites unless the user explicitly asks and understands the consequences.
- Never amend a commit unless the user explicitly requested amend, or the commit succeeded and a hook auto-modified files that need including - and only when that commit has not been pushed and was created in this session. If a commit fails or is rejected by a hook, fix the issue and create a **new** commit; never amend a failed commit.

Write commit messages via HEREDOC:

```bash
git commit -m "$(cat <<'EOF'
<subject line>

<body, if any>
EOF
)"
```

### Phase 4: Push

Push only when the user's request included pushing:

```bash
git push -u origin "$(git branch --show-current)"
```

If push fails (for example, diverged history), report the exact error and ask before force-pushing or rebasing.

### Phase 5: Output contract

Report:

1. **Doc sync**: files updated, or "none needed".
2. **Gate**: command run and result, or "no gate found".
3. **Commits**: subject line per commit (and cluster rationale if more than one).
4. **Push**: remote and branch, or why it was skipped.
5. **Remaining dirty state**: any `git status --short` lines left over.

After a successful commit or push, if the diff touched architecture or left known follow-up work, offer a short "Next steps" note in the response (not a new file). Do not implement further unless asked.

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
- Prefer `uv run ...`; activate the project virtualenv only when direct interpreter workflows are explicitly needed

## Related skills

- `write-a-skill`: use only for creating or refactoring skills.
- `research`: use when external source-backed guidance is required.
- `advisor`: escalate hard forks, contract risk, or repeated failure for readonly PLAN/CORRECTION/STOP guidance.
- `grill-with-docs`: pressure-test plans against local contracts before committing to an approach.
- `ponytail`: YAGNI / minimal-diff mode; does not override hard exclusions or project invariants.
- `improve-codebase-architecture`: deepen architecture review when structural debt or boundary drift is the task.
- `handoff`: package session transfer when pausing or switching agents (not a substitute for commit hygiene).

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
