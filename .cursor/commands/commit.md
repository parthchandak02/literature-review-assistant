# Commit

Single entrypoint for landing changes: probe, doc sync, quality gate, clustered commits, optional push, and hook repair when needed.

## Canonical source

- Full workflow: `.cursor/skills/general-rules/SKILL.md` (Git Security and Commit Practices)
- Lifecycle routing: `.cursor/docs/INDEX.md`

## Execution sequence

1. **Probe** (Phase 0): `git status --short`, `git branch -vv`, `git diff --stat`.
2. **Doc sync** (Phase 1): if the diff touches architecture, phases/checkpoints, API contracts, persistence/schema, frontend phase alignment, or `.cursor/` agent docs, walk the **Docs-to-Code Parity Checklist** and **Verification Gates** in `.cursor/docs/IMPLEMENTATION_STATUS.md` before committing.
3. **Quality gate** (Phase 2): `make release-check` or `make local-ci` when present; otherwise ruff/pytest/`pnpm typecheck` on touched areas.
4. **Hook repair** (only if hooks are missing or fail): follow the **Hook repair** subsection in `general-rules` (Python `pre-commit` + optional frontend local hooks; do not improvise Husky or a competing stack).
5. **Commit** (Phase 3): stage explicitly, cluster by intent, HEREDOC messages, confirm scope with the user before committing.
6. **Push** (Phase 4): only when the user asked to push.
7. **Report** (Phase 5): doc sync, gate, commits, push, remaining dirty state.

Small localized fixes that do not touch contract surfaces may skip the full IMPLEMENTATION_STATUS checklist; use judgment.

## Safety rules

- Never stage secrets, credential files, `runs/**`, runtime DB files, or generated artifacts.
- Never force-push to `main`/`master`.
- Never skip user confirmation before commit or push.
- Push only when explicitly requested.
