---
name: handoff
description: Produces concise handoff context so another agent can continue work without re-discovery. Use when switching sessions, pausing substantial work, or transferring ownership of an in-flight task.
argument-hint: "What should the next session focus on?"
disable-model-invocation: true
---

# Handoff

Create a compact handoff for a fresh agent to continue quickly and safely.

If the user provides arguments, treat them as the next-session objective and tailor the handoff to that scope.

## Primary mode

Default to handoff content in chat.
Create a markdown file only when the user explicitly asks for a file artifact.

If a file is requested, use a temp path from:

```bash
mktemp -t handoff-XXXXXX.md
```

Read the generated file before writing to it.
Write the document to the path `mktemp` prints, then print that absolute path to the user.

If `mktemp` is unavailable or blocked, ask the user for a path, or use `$TMPDIR` / `/tmp` with a unique name such as `handoff-<timestamp>.md`. Do not commit scratch handoffs to the repo without consent.

Optional section labels and stack bullets: [references/RUNTIME-TEMPLATE.md](./references/RUNTIME-TEMPLATE.md).

## Required sections

1. Session objective (one line: what the session was trying to achieve)
2. Completed work
3. In-progress work
4. Blockers and risks
5. Exact next actions (ordered, first action first)
6. Landmines - decisions made and why; dead ends already ruled out
7. Suggested skills/tools for next agent (sibling skills that fit the next work)
8. Reference artifacts (paths/URLs only)

## Suggested sibling skills

Only list skills that fit the next work. Omit the rest.

- `grill-with-docs` - plan / terminology still fuzzy
- `prototype` - need to try a design before committing
- `improve-codebase-architecture` - deepening or seam work
- `research` - version-sensitive or contested facts
- `advisor` - costly fork, stuck, or need a second opinion
- `ponytail` - risk of over-building; force the minimal path

## Repository-specific guidance

- Reference canonical docs via `.cursor/docs/INDEX.md` when they affect next steps.
- Include concrete verification commands when relevant (tests, replay checks, parity checks).
- Point to specific code paths in `src/` or `frontend/src/` that were touched or should be touched next.

## Stack-specific run state

Include when the next session will run or verify the app. Infer focus from recent work; if several apply, prefer what the next session will focus on.

### Python / FastAPI backend

- Python toolchain: `uv` (preferred).
- Entry commands: `uv run python -m src.main ...`, `uv run pytest ...`, `make local-ci` / `make release-check`.
- Important env var *names* only (never values); `pyproject.toml` / `config/` notes when relevant.
- After `src/` changes: `pm2 restart litreview-api`.

### React / Vite frontend

- Package manager: `pnpm` under `frontend/`.
- Key scripts: `pnpm dev`, `pnpm build`, `pnpm typecheck`.
- Dev server URL or proxy notes when known.
- For production URL verification: `cd frontend && pnpm build` then `pm2 restart litreview-api`.

### PM2 processes

Exact names: `litreview-api`, `litreview-ui`, `litreview-tunnel`.
Before claiming local/online verification, note `pm2 list` status for the processes the next session needs.

## De-duplication rule

Do not duplicate content already captured in plans, PR descriptions, ADRs, issues, commits, or diffs.
Link or cite those artifacts instead.

Point at artifacts that already hold the truth:

- Code: file paths under `src/` or `frontend/src/` (and line ranges where useful), not pasted bodies.
- Docs: `.cursor/docs/INDEX.md`, ADRs, `AGENTS.md`, README, issue/PR URLs.
- Git: branch name, short `git status` summary, unpushed commits by hash/subject.
- Open PR / ticket by URL or key.

## Guardrails

- Do not invent progress; mark unknowns as unknown.
- Do not include secrets. Prefer env var *names* over values.
- Keep it short, factual, and execution-ready.
- ASCII only. Use hyphen (`-`), not em or en dashes.
