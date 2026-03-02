# Session Bootstrap

Orient yourself at the start of every new chat session before making any plans or edits.
Execute ALL steps below immediately -- do not skip any step even for seemingly simple requests.

---

## Step 1 -- Read the authoritative project docs

Read these two files in full. They are the ground truth for architecture, phase status, and
every module's responsibility:

- `spec.md` -- full technical specification (all 8 phases, acceptance criteria, implementation status)
- `README.md` -- quick-start, production URLs, PM2 process names

Also read the project overview rule which maps every directory:
- `.cursor/rules/core/project-overview-always.mdc`

The Known Gotchas section at the bottom of `project-overview-always.mdc` contains hard-won
session knowledge. Check it before assuming any behavior about PRISMA, run directories, or
frontend builds.

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

## Step 3 -- Check process health

```bash
pm2 list
pm2 logs litreview-api --lines 20
```

Verify `litreview-api` (port 8001 dev / 8000 prod) and `litreview-ui` are online.
If `litreview-api` is stopped or erroring, fix that before starting new work.

---

## Step 4 -- Production deploy reminder

The production URL (`https://litreview.parthchandak.info`) is served by FastAPI on port 8000
via Cloudflare tunnel. It serves the built `frontend/dist/` -- NOT the Vite dev server.

After any frontend code change, rebuild before expecting production to reflect it:

```bash
cd frontend && pnpm build && cd ..
pm2 restart litreview-api
```

The Vite dev server (localhost:5173) picks up changes automatically; the production URL does not.

---

## Orientation checklist (confirm before proceeding)

- [ ] Read spec.md and README.md
- [ ] Read .cursor/rules/core/project-overview-always.mdc (especially Known Gotchas)
- [ ] Reviewed last 5 commit messages and touched files
- [ ] Noted any uncommitted changes in git status
- [ ] Confirmed pm2 process health
