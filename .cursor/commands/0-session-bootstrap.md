# Session Bootstrap

Orient yourself at the start of every new chat session before making any plans or edits.
For planning or editing tasks, execute all steps below before proceeding.
For quick read-only questions, Steps 1-2 are required and Steps 3-5 are optional.

---

## Step 1 -- Read the authoritative project docs

Read these files in full. They describe architecture, phase status, and module responsibilities.
Cross-check them against each other -- they occasionally drift as the codebase evolves faster
than any single doc:

- `spec.md` -- full technical specification (all 8 phases, acceptance criteria, implementation status)
- `README.md` -- quick-start, production URLs, PM2 process names
- `.cursor/rules/core/project-overview-always.mdc` -- maps every directory; ALWAYS-ON so it loads automatically.
  Pay special attention to the **"Fix Processes, Not Individual Runs"** section -- the most important
  engineering constraint in this codebase. Never manually edit files under `runs/`.
- `.cursor/rules/core/gotchas-agent.mdc` -- operational gotchas (PRISMA, run directories, frontend builds,
  runtime quirks, and known pipeline bug fix locations). Check before assuming any behavior that "should work but doesn't."

NOTE: `spec.md` and `README.md` are maintained manually and may lag recent code changes.
When they contradict the code, trust the code. When they contradict `.cursor/rules/core/project-overview-always.mdc`,
that rule is closer to current truth. Document any confirmed drift in `gotchas-agent.mdc`.

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

- [ ] Read spec.md and README.md
- [ ] Read .cursor/rules/core/project-overview-always.mdc and gotchas-agent.mdc
- [ ] Understood the "Fix Processes, Not Individual Runs" principle from project-overview-always.mdc
- [ ] Reviewed last 5 commit messages and touched files
- [ ] Noted any uncommitted changes in git status
- [ ] Selected a workflow ID and ran quick replay validation (or explicitly deferred for non-pipeline task)
- [ ] Confirmed pm2 process health
- [ ] Ran ruff + pnpm fix + pnpm typecheck (or intentionally deferred on dirty tree)
