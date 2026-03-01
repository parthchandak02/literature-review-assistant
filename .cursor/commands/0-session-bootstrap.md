# Session Bootstrap

Orient yourself at the start of every new chat session before making any plans or edits.
Run all steps below immediately -- do not skip them even for seemingly simple requests.

## Step 1 -- Understand recent changes

```bash
git log --oneline -10             # what changed across recent sessions
git log --name-only --oneline -5  # which specific files changed in the last 5 commits
git status --short                # any uncommitted edits right now
```

Read the commit messages and file list carefully. They tell you what a previous agent
already did so you do not repeat work or undo changes.

## Step 2 -- Check process health

```bash
pm2 list                          # verify litreview-api (port 8001) and litreview-ui are online
pm2 logs litreview-api --lines 20 # catch any recent backend crashes
```

If `litreview-api` is stopped or erroring, fix that before starting new work.

## Step 3 -- Re-read the project overview

`project-overview-always.mdc` is the authoritative map of every backend module (`src/`)
and frontend component (`frontend/src/`). Re-read the relevant section before touching
an unfamiliar module. The Known Gotchas section at the bottom contains hard-won session
knowledge -- check it before assuming any behavior.

## Step 4 -- Production deploy reminder

The production URL (`https://litreview.parthchandak.info`) is served by FastAPI on port 8000
via Cloudflare tunnel. It serves the built `frontend/dist/` -- NOT the Vite dev server.

After any frontend code change, rebuild before expecting production to reflect it:

```bash
cd frontend && pnpm build && cd ..
pm2 restart litreview-api
```

The Vite dev server (localhost:5173) picks up changes automatically; the production URL does not.
