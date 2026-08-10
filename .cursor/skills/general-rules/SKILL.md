---
name: general-rules
description: Cross-cutting engineering defaults for uv, ruff, diagnose/TDD, scripting, and documentation discipline. Use for broad implementation guardrails unless bootstrap, commit, or a domain skill owns the workflow.
---

# General Project Rules

Cross-cutting defaults for this repository. For session startup use `bootstrap`. For commit/push use `commit`.

## Workflow pointers

| Task | Skill |
|------|-------|
| Session startup | `bootstrap` |
| Commit / push / hooks | `commit` |
| Replay / resume drill | `resume` |
| Skill authoring | `author` |
| External research | `research` |

## Documentation standards

Keep documentation minimal and focused on getting started. Prioritize "How to use" in README.md.

- Only create additional `.md` files when explicitly requested
- Keep documentation short, utilitarian, no fluff
- For multi-step work, prefer built-in todo/task tracking instead of tracking markdown files

## Engineering patterns

### Diagnose loop (root-cause first)

1. Reproduce with a deterministic command
2. Minimize scope to the smallest failing unit
3. Form 1-2 hypotheses and rank by likelihood
4. Instrument with focused logs/assertions or DB/query checks
5. Fix at source in `src/` or `frontend/src/` (never patch `runs/` artifacts)
6. Add regression coverage and rerun the failing path

### TDD vertical slice

- One failing test proving user-visible behavior first
- Minimum code to pass, refactor after green
- Thin slices across API -> orchestration -> UI

### Zoom-out before deep edits

- Identify entrypoints, typed boundaries, canonical source-of-truth tables/files
- Confirm lifecycle stage via `docs/CONTEXT.md`
- Note blast radius (orchestration, API contract, persistence, UI)

## Script organization

1. **Recurring scripts** - automate frequent workflows (backend/frontend start, deploys, batch jobs)
2. **Temporary scripts** - one-off debugging; clean up after use

Name clearly, document at top, prefer Bash for speed and Python for complex automation.

## Python environment

Use `uv` for dependency management and execution.

- Prefer `uv run ...` for Python commands
- Activate the project virtualenv only when direct interpreter workflows are explicitly needed

## Related skills

- `bootstrap`, `commit`, `resume` - session and ship workflows
- `author` - skill creation/refactor
- `research` - external source-backed guidance
- `advisor` - readonly PLAN/CORRECTION/STOP escalation
- `grill` - pressure-test plans against local contracts
- `ponytail` - YAGNI / minimal-diff mode
- `architecture` - structural boundary and debt review
- `handoff` - session transfer packaging

## Code quality (ruff)

If `[tool.ruff]` exists in `pyproject.toml`:

- Before edits: `ruff check .`
- After edits: `ruff check --fix .` (or `--fix --unsafe-fixes` when appropriate)
- Before commit: `ruff check src/`

Skip ruff steps if not configured.
