# Session Bootstrap

Orient yourself at the start of every new chat session before making any plans or edits.
For planning or editing tasks, execute all steps below before proceeding.
For quick read-only questions, Steps 1, 1.5 (lightweight pack), and 2 are required; Steps 3-5 are optional.

---

## Step 1 -- Route through canonical docs first

If not already loaded, read `AGENTS.md` first.
Read `.cursor/docs/INDEX.md` first, then follow its lifecycle routing.
Use `.cursor/docs/API_ENDPOINTS.md` only when checking endpoint parity compatibility.

Required baseline reads:

- `.cursor/docs/INDEX.md` -- canonical router (single lifecycle narrative)
- `.cursor/rules/core/project-overview-always.mdc` -- always-on invariants and source-of-truth paths
- `.cursor/rules/core/gotchas-agent.mdc` -- operational edge cases and known pitfalls
- `README.md` -- user-facing setup and operations
- `.cursor/docs/API_ENDPOINTS.md` -- endpoint parity anchor (Section 10.1), only when API contract/parity work is involved

Then read only task-specific docs/skills referenced by `.cursor/docs/INDEX.md`.

NOTE: `.cursor/docs/*` and `README.md` are maintained manually and may lag recent code changes.
When they contradict the code, trust the code. When they contradict any always-on rule in `.cursor/rules/core/`,
the rule layer is closer to current truth; then verify against code. Document any confirmed drift in `gotchas-agent.mdc`.

---

## Step 1.5 -- Repomix repo snapshot (structural ground truth)

Purpose: align the session with what the repository **actually** contains (paths, density, and searchable text), not only the curated docs from Step 1.

**When the Repomix MCP server (`user-repomix`) is available:**

1. Call `pack_codebase` with `directory` set to the **absolute path of this repository root** (the folder that contains `README.md` and `pyproject.toml`).
2. Recommended `ignorePatterns` to keep packs small and safe:
   `**/node_modules/**,**/dist/**,**/runs/**,**/.venv/**,**/frontend/dist/**`
3. Read the tool response carefully: `directoryStructure`, file counts / token metrics, and store **`outputId`** for follow-up searches on the same pack.
4. Use `grep_repomix_output` with that `outputId` to locate entrypoints, symbols, and config keys before opening many files at random.
5. **Planning or editing tasks:** add `includePatterns` scoped to the user request (examples: `src/manuscript/**/*.py`, `frontend/src/**/*.ts`, `frontend/src/**/*.tsx`) **plus** the Step 1 doc paths (`README.md`, `AGENTS.md`, `.cursor/docs/**/*.md`) so contracts and code land in one searchable surface.
6. **Quick read-only questions:** still run Step 1.5, but keep the pack small (docs + one subtree, or docs-only) so startup stays fast.
7. If a prior Repomix output file already exists on disk and is fresh enough, you may call `attach_packed_output` with `path` to reuse it; re-pack when `git status` shows large structural changes you have not captured yet.

**When Repomix is unavailable:** approximate the same intent with `git ls-files` (optionally scoped) and workspace `rg`, then read files directly.

**Token discipline:** if the reported token total is too large, narrow `includePatterns`, tighten `ignorePatterns`, or set `compress` to true only when you truly need whole-repo breadth (see Repomix tool descriptions).

---

## Step 2 -- Understand recent changes

Run all three commands and read the output carefully:

```bash
git log --oneline -10
git log --format="%H%n%s%n%b%n---FILES---" --name-only -5
git status --short
```

The detailed log (second command) shows you:
- Exact commit message and body for each of the last 5 commits
- Which files each commit touched

This tells you what a previous agent already did so you do not repeat work or undo changes.
Pay special attention to any uncommitted modifications (M) and untracked files (??) in git status.

---

## Step 2.5 -- Select a real workflow for replay validation

For any pipeline change (screening, extraction, quality, writing, export), select an existing
workflow ID and run a quick replay validation before editing:

```bash
uv run python scripts/validate_workflow_replay.py --workflow-id wf-XXXX --profile quick
```

Use local workflow data only (no synthetic dummy fixtures) when validating end-to-end behavior.
All replay evidence is written to validation tables in that workflow's `runtime.db`.
If the current task is strictly read-only planning/research, explicitly defer this step because it writes validation evidence.

---

## Step 3 -- Check process health

```bash
pm2 list
pm2 logs litreview-api --lines 20 --nostream
```

Verify `litreview-api` (port 8001 for dev and PM2-served production process) and `litreview-ui` are online.
PM2 process names are `litreview-api`, `litreview-ui`, and `litreview-tunnel`.
`litreview-tunnel` is optional unless you are validating the production URL path.
Do NOT use shorthand aliases like `api` or `ui` -- those are NOT configured.
If `litreview-api` is stopped or erroring, fix that before starting new work.

---

## Step 4 -- Production deploy reminder

The production URL (`https://litreview.parthchandak.info`) is served by FastAPI on port 8001
via Cloudflare tunnel. It serves the built `frontend/dist/` -- NOT the Vite dev server.

After any frontend code change, rebuild before expecting production to reflect it:

```bash
cd frontend && pnpm build && cd ..
pm2 restart litreview-api
```

The Vite dev server (localhost:5173) picks up changes automatically; the production URL does not.

---

## Step 5 -- Lint and fix (high-level health)

WARNING: these commands modify files (`ruff format`, `pnpm fix`).
If `git status --short` is not clean, run this step only when you intend to keep those edits
or after you stash/commit current work.

```bash
uv run ruff check . --fix && uv run ruff format .
cd frontend && pnpm fix && pnpm typecheck
```

---

## Orientation checklist (confirm before proceeding)

- [ ] Read `AGENTS.md` and `.cursor/docs/INDEX.md`
- [ ] Ran Repomix `pack_codebase` (or `attach_packed_output`) and captured `outputId`; used `grep_repomix_output` when hunting symbols, or noted MCP unavailable and used `git ls-files` / `rg` instead
- [ ] Read only the task-scoped docs and skills selected by `.cursor/docs/INDEX.md`
- [ ] Read README.md and (if touching API contracts) `.cursor/docs/API_ENDPOINTS.md` Section 10.1 parity table
- [ ] Read .cursor/rules/core/project-overview-always.mdc and gotchas-agent.mdc
- [ ] Understood the src/-only fix / no `runs/` patches principle from project-overview-always.mdc
- [ ] Reviewed last 5 commit messages and touched files
- [ ] Noted any uncommitted changes in git status
- [ ] Selected a workflow ID and ran quick replay validation (or explicitly deferred for non-pipeline task)
- [ ] Confirmed pm2 process health
- [ ] Ran ruff + pnpm fix + pnpm typecheck (or intentionally deferred on dirty tree)
