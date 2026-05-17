# Pre-Commit Workflow

Use this command as a thin launcher for commit/push execution.

## When to refresh docs and parity checks

If a change is **high level** (architecture, runtime phases/checkpoints, API contracts, DB schema or canonical tables, frontend phase/resume alignment, or `.cursor/` rules/skills), you must reconcile docs and validation **before** committing:

1. Walk the **Docs-to-Code Parity Checklist** in `.cursor/docs/IMPLEMENTATION_STATUS.md`.
2. Run the **Verification Gates** there when applicable (endpoint parity, replay script, tests, frontend lint/typecheck).
3. Then continue with the commit sequence in `general-rules`.

Small, localized fixes that do not touch those surfaces can skip the full checklist; use judgment.

## Canonical source

- Primary workflow owner: `.cursor/skills/general-rules/SKILL.md`
- Hook setup owner: `.cursor/skills/setup-pre-commit/SKILL.md`

## Quick execution sequence

1. Run the commit/push sequence from `general-rules`.
2. If hooks are missing or broken, run `setup-pre-commit` first.
3. Confirm staged scope and explicit user approval before commit/push.
4. Push only when explicitly requested.

## Safety Rules

- Never stage secrets, runtime artifacts, or DB files.
- Never force-push to `main`/`master`.
- Never skip user confirmation before commit/push.
- If hook setup is requested, use `setup-pre-commit` (do not improvise an unrelated hook stack).
