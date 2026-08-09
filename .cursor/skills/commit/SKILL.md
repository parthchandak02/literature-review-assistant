---
name: commit
description: Lands changes with probe, doc sync, quality gate, clustered commits, optional push, and hook repair. Use when the user asks to commit, push, land changes, or invokes /commit.
disable-model-invocation: true
---

# Commit

Canonical landing workflow for this repo. Push is never automatic: only push when the user explicitly asks (or says "commit and push" / "land this"). If push intent is ambiguous, ask once. Get explicit confirmation before commit or push.

## Sequence overview

```
Phase 0  Probe          git status, branch, diff (scope + intent)
Phase 1  Doc sync       update docs the diff makes stale
Phase 2  Quality gate   run project verify/test/lint
Phase 3  Commit         cluster staging, one concern per commit
Phase 4  Push           only when the user asked
Phase 5  Report         output contract + optional next steps
```

## Phase 0: Probe

```bash
git status --short
git branch -vv
git diff --stat
```

Confirm: not detached HEAD, a tracking remote exists if pushing is in scope, and the changes match what the user described.

## Phase 1: Doc sync

When the diff touches contracts (architecture, phases/checkpoints, public API, persistence/schema, frontend phase alignment, or `.cursor/` agent docs):

1. Update matching docs under `.cursor/docs/` (route via `.cursor/docs/INDEX.md`).
2. Run **Before you commit** in `.cursor/docs/IMPLEMENTATION_STATUS.md`.
3. Keep `AGENTS.md` and skill catalog (`.cursor/skills/README.md`) consistent if paths changed.

Small localized fixes may skip the full checklist; use judgment.

## Phase 2: Quality gate

1. Prefer `make release-check` when release-bound.
2. Otherwise `make local-ci` when present.
3. Else: `ruff check` / `uv run pytest` on touched areas; `pnpm typecheck` (and lint/build) for frontend.

### Hook repair (only when hooks fail or are missing)

Default to Python `pre-commit` + optional frontend local hooks. Do not improvise Husky or a competing stack.

1. Inspect `.pre-commit-config.yaml`, Ruff config, frontend lint scripts, CI. Extend what exists.
2. `uv add --dev pre-commit` (or `uv tool install pre-commit` when deps must not change).
3. Pin Ruff hook `rev` at install time if missing; keep existing pin unless upgrading.
4. Optional: `pnpm -C frontend lint`, `pnpm -C frontend typecheck` (scoped).
5. `uv run pre-commit install && uv run pre-commit run --all-files`

## Phase 3: Clustered commits

- Smallest coherent units; split unrelated concerns.
- Do not mix docs/rules churn with behavioral code in one commit.
- Stage explicitly (`git add -- <paths>`), not `git add -A` when tree is mixed.

Hard exclusions unless user explicitly requests: secrets/credential files, `runs/**`, runtime DB files, ignored files in staging.

Safety: no `git config` changes; no force/history rewrite without explicit user consent; no amend on failed commits.

```bash
git commit -m "$(cat <<'EOF'
<subject line>

<body, if any>
EOF
)"
```

## Phase 4: Push

Only when requested:

```bash
git push -u origin "$(git branch --show-current)"
```

## Phase 5: Output contract

Report: doc sync, gate result, commit subjects, push status, remaining dirty state.

## Safety rules

- Never stage secrets, credential files, `runs/**`, runtime DB files, or generated artifacts.
- Never force-push to `main`/`master`.
- Never skip user confirmation before commit or push.
