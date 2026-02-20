# LitReview Web UI -- Frontend Specification

**Document Type:** Architecture Spec and Recipe
**Date:** Feb 2026
**Purpose:** Single source of truth for the LitReview web frontend. Covers stack decisions, architecture, key patterns, design system, and how-to guides for extending the UI.

---

## 1. Purpose and Scope

LitReview exposes a local single-user web dashboard for the systematic review pipeline. It is NOT a multi-tenant SaaS product:

- No authentication or authorization
- No remote server -- backend and frontend both run on the user's machine
- Users bring their own API keys (Gemini, OpenAlex, IEEE); keys are passed in the request body directly to the local FastAPI process and never logged or stored to disk
- Designed for researchers and developers running one review at a time

The CLI (`uv run python -m src.main`) and the web UI are fully independent. Adding or removing the frontend does not affect the backend pipeline.

---

## 2. Stack

| Layer | Technology | Version | Notes |
|-------|-----------|---------|-------|
| Backend API | FastAPI + Uvicorn | latest | `src/web/app.py` |
| Streaming | sse-starlette | latest | Server-Sent Events for live log delivery |
| DB access | aiosqlite | latest | Async read-only queries to SQLite runs |
| Frontend framework | React + TypeScript | 18 / 5 | Strict TypeScript, no `any` at boundaries |
| Build tool | Vite | 7 | Hot reload in dev, chunk splitting in prod |
| Package manager | pnpm | 10 | Workspace in `frontend/` |
| UI components | shadcn/ui | latest | Radix-based, copy-owned in `src/components/ui/` |
| Styling | Tailwind CSS | 4 | Utility classes only, no CSS-in-JS |
| Charts | Recharts | latest | `CostView.tsx` bar charts |
| SSE client | @microsoft/fetch-event-source | latest | Robust SSE with abort support |

---

## 3. Directory Layout

```
frontend/
  index.html                  -- Vite HTML entry, title "LitReview"
  vite.config.ts              -- React plugin, @ alias, /api proxy to :8000
  tsconfig.app.json           -- ES2023 target, @ path alias
  src/
    main.tsx                  -- Root render, forces dark class on <html>
    index.css                 -- Tailwind import, shadcn CSS vars, dark scrollbars
    App.tsx                   -- Shell: sidebar + header + lazy view router
    lib/
      api.ts                  -- All typed fetch wrappers + SSE event types
      utils.ts                -- cn() Tailwind class merger (required by shadcn)
    hooks/
      useSSEStream.ts         -- Connects to /api/stream/{run_id}, parses events
      useCostStats.ts         -- Aggregates api_call events into cost/token totals
    components/
      Sidebar.tsx             -- Run list (chat-style): "+" for new review, live run at top, history below; status-colored left borders; stats strip per card
      RunForm.tsx             -- YAML textarea + API key inputs + submit
      LogStream.tsx           -- Monospace scrollable event log with filter chips
      ResultsPanel.tsx        -- Download links and image previews
      ui/                     -- shadcn copy-owned components (button, input, ...)
        feedback.tsx          -- Shared EmptyState, FetchError, LoadingPane components
    views/
      SetupView.tsx           -- New Review: minimal heading + RunForm
      RunView.tsx             -- 4-tab container for a selected run (Activity, Results, Database, Cost)
      ActivityView.tsx        -- Phase timeline + stats strip + filter chips + event log (live SSE or historical fetch)
      CostView.tsx            -- Recharts bar chart + model/phase cost tables
      DatabaseView.tsx        -- Tabbed DB explorer (Papers / Screening / Costs)
      ResultsView.tsx         -- Download panel for completed runs
      HistoryView.tsx         -- Past runs table; "Open" attaches historical run
```

---

## 4. Architecture

### 4.1 Two-Process Split

```
[browser]
    |  HTTP GET/POST /api/*
    |  GET /api/stream/{run_id}  (SSE)
    v
[FastAPI -- src/web/app.py  -- port 8000]
    |  asyncio.create_task()
    |  WebRunContext (emits JSON events to asyncio.Queue)
    v
[run_workflow() -- src/orchestration/workflow.py]
    |  aiosqlite
    v
[logs/{date}/{topic}/run_*/runtime.db]
[logs/workflows_registry.db]
```

In production, Vite's build output (`frontend/dist/`) is served as static files by FastAPI via `StaticFiles`. In development, Vite dev server runs on port 5173 and proxies `/api/*` to port 8000 (configured in `vite.config.ts`).

### 4.2 Live Run SSE Streaming

```
run_workflow()
  --> WebRunContext.emit(event_dict)
       --> asyncio.Queue.put(event_dict)       (live queue)
       --> _RunRecord.event_log.append()       (in-memory replay buffer)
            --> /api/stream/{run_id}  (EventSourceResponse)
            --> /api/run/{run_id}/events  (replay buffer snapshot)
                 --> fetchRunEvents() prefetch in useSSEStream.ts  (dedup replay buffer)
                      --> fetchEventSource() live stream (dedup merges new events)
                           --> setState({ events: dedup([...prior, ...live]) })
                                --> all views re-render with new data
```

Key files:
- `src/orchestration/context.py` -- `WebRunContext` dataclass with typed `emit` methods
- `src/web/app.py` -- `_run_wrapper()`, `stream_run()` endpoint
- `frontend/src/hooks/useSSEStream.ts` -- React hook that manages the SSE connection

Every event has a `type` discriminator. The union type `ReviewEvent` in `api.ts` lists all variants with their fields.

### 4.3 History / Attach Pattern

Past runs live in `logs/workflows_registry.db`. The frontend cannot open SQLite directly, so:

1. `GET /api/history` -- backend reads the registry and returns `HistoryEntry[]`
2. User clicks "Open" on a past run
3. `POST /api/history/attach` -- backend creates a completed `_RunRecord` in `_active_runs` with `db_path` set, returns a short `run_id`
3b. Backend calls `_load_event_log_from_db(db_path)` and populates `record.event_log` from the persisted `event_log` table so LogView and `useSSEStream` can replay historical events via `GET /api/run/{run_id}/events`.
4. Frontend sets this `run_id` as the current run; `hasRun` becomes true; all tabs unlock
5. `GET /api/db/{run_id}/papers|screening|costs` -- existing DB explorer endpoints now serve data from the historical `runtime.db`

### 4.4 Additional Run Endpoints

Two endpoints exist beyond the DB explorer that are not part of the attach flow but are used by ResultsView and ActivityView:

| Endpoint | Response | Used by |
|---|---|---|
| `GET /api/run/{run_id}/events` | `{ events: ReviewEvent[] }` -- full replay buffer (in-memory for live runs, loaded from DB for historical) | `useSSEStream` prefetch, `ActivityView` historical mode |
| `GET /api/run/{run_id}/artifacts` | `{ artifacts: Record<str, str> }` -- label to absolute path map from `run_summary.json` | `ResultsView` download panel |
| `GET /api/workflow/{workflow_id}/events` | `{ events: ReviewEvent[] }` -- events loaded directly from `event_log` table by workflow ID | `ActivityView` when attaching historical runs without a live `run_id` |

### 4.5 Client-Side Cost Tracking

No backend computation needed for cost. The `useCostStats` hook iterates the `events` array in memory, filters for `type === "api_call" && status === "success"`, and accumulates totals by model and phase. This runs on every re-render with no extra network requests.

---

## 5. Design System

All colors come from Tailwind utility classes. No custom CSS variables are added to `index.css` beyond the shadcn defaults.

| Role | Class | Hex |
|------|-------|-----|
| Page background | `bg-[#09090b]` | #09090b |
| Card background | `bg-zinc-900` | #18181b |
| Card border | `border-zinc-800` | #27272a |
| Muted text | `text-zinc-500` | #71717a |
| Body text | `text-zinc-200` | #e4e4e7 |
| Active accent | `bg-violet-600` / `text-violet-400` | #7c3aed / #a78bfa |
| Success / cost | `text-emerald-400` | #34d399 |
| Error | `text-red-400` | #f87171 |
| Warning | `text-amber-400` | #fbbf24 |

**Typography:** Inter via Google Fonts (loaded in `index.html`). `font-mono` for log output and cost figures.

**Sidebar:** Fixed-width run list (~280px). Not collapsible. Each run card has a status-colored left border (2px): emerald = completed, violet = running/connecting, red = error/failed, amber = cancelled, zinc = idle/unknown.

**Active run card:** `bg-zinc-800/60 border-l-2 border-violet-500`

**Run card stats strip:** `papers_found | papers_included | artifacts_count | $cost` in `text-zinc-400 font-mono text-xs`.

---

## 6. Key Patterns

### 6.1 Typed API boundary

Every function in `api.ts` accepts and returns typed interfaces. Never use `any` or untyped `dict` at the boundary between frontend and backend.

```typescript
// Good
export async function fetchPapers(runId: string, ...): Promise<{ total: number; papers: PaperRow[] }>

// Bad
export async function fetchPapers(runId: string): Promise<any>
```

### 6.2 Lazy view loading

Every view is lazy-loaded in `App.tsx` to keep the initial bundle small:

```typescript
const HistoryView = lazy(() =>
  import("@/views/HistoryView").then((m) => ({ default: m.HistoryView }))
)
```

Each view gets its own chunk in the Vite build output.

### 6.3 Run-centric tab model

The main content area always renders a `RunView` for the selected run. `RunView` has four fixed tabs: Activity, Results, Database, Cost. The selected tab is persisted in localStorage so switching between runs keeps the tab you were on. Only starting a new run resets the tab to Activity.

The old `NAV_ITEMS` / `requiresRun` pattern no longer exists. The sidebar is a run list: selecting a run sets `selectedRun` in App state; `RunView` renders immediately with that run's data. The "+" button in the sidebar header opens `SetupView` to start a new run.

### 6.4 SSE heartbeat

The backend sends a `heartbeat` event every 15 seconds of inactivity to keep the connection alive through long phases. The `useSSEStream` hook ignores heartbeat events (`if (ev.event === "heartbeat") return`).

---

## 7. How to Add a New Tab to RunView

1. Create `frontend/src/views/MyView.tsx` exporting a named component `MyView`
2. Add the tab id to the `RunTab` union type in `RunView.tsx`
3. Add the tab label to the `TABS` array in `RunView.tsx`
4. Add a lazy import in `RunView.tsx`:
   ```typescript
   const MyView = lazy(() => import("@/views/MyView").then((m) => ({ default: m.MyView })))
   ```
5. Add a `case "mytab":` in the tab content renderer inside `RunView.tsx`
6. Run `pnpm run build` to confirm zero TypeScript errors

Note: the sidebar is a run list and does not need to change when adding new tabs. Tabs are scoped to `RunView`.

---

## 8. How to Add a New Backend Endpoint

1. Add the route in `src/web/app.py`:
   ```python
   @app.get("/api/my-endpoint")
   async def my_endpoint(...) -> MyResponseModel:
       ...
   ```
2. Add a Pydantic response model to `app.py` if needed
3. Add a typed fetch function to `frontend/src/lib/api.ts`:
   ```typescript
   export interface MyResponse { ... }
   export async function fetchMyData(...): Promise<MyResponse> {
     const res = await fetch(`/api/my-endpoint`)
     if (!res.ok) throw new Error(...)
     return res.json() as Promise<MyResponse>
   }
   ```
4. Import and call the fetcher in the relevant view

---

## 9. Dev Workflow

### Start both processes

The recommended approach is [Overmind](https://github.com/DarthSim/overmind) (MIT, macOS/Linux).
It reads `Procfile.dev` at the project root and manages both processes under a shared tmux session.

One-time setup:
```bash
brew install overmind    # tmux is pulled in automatically
```

Start everything:
```bash
./bin/dev
# or equivalently: overmind start
```

`Procfile.dev` defines the two processes:
```
api: uv run uvicorn src.web.app:app --port 8000 --reload
ui:  cd frontend && pnpm run dev -- --port 5173
```

`.overmind.env` (committed) sets defaults:
```
OVERMIND_PROCFILE=Procfile.dev
OVERMIND_AUTO_RESTART=api,ui
OVERMIND_NO_PORT=1
```

Key Overmind commands:
```bash
overmind connect api      # drop into the backend tmux pane (Ctrl-b d to detach)
overmind connect ui       # drop into the frontend tmux pane
overmind restart api      # hot-restart backend without touching frontend
overmind start -D         # run as a daemon (survives terminal close)
overmind echo             # tail daemon logs
overmind quit             # stop the daemon
```

Open `http://localhost:5173`. The Vite dev server proxies `/api/*` to `:8000`.

Alternatively, run each in a separate terminal (no Overmind needed):
```bash
# Terminal 1
uv run uvicorn src.web.app:app --reload --port 8000
# Terminal 2
cd frontend && pnpm run dev
```

### Build for production

```bash
cd frontend && pnpm run build
```

Output: `frontend/dist/`. FastAPI serves this automatically via `StaticFiles` if the directory exists. Open `http://localhost:8000`.

### Lint check

```bash
cd frontend && pnpm run build   # tsc -b catches all type errors
```

There is no separate ESLint step required; TypeScript strict mode catches most issues.

---

## 10. SSE Event Reference

All events emitted by `WebRunContext` (`src/orchestration/context.py`) and consumed by `useSSEStream`.
Every event includes a `ts` field (UTC ISO-8601 timestamp) injected automatically by `_emit()`.
The `ReviewEvent` discriminated union in `frontend/src/lib/api.ts` is the canonical TypeScript type.

| type | Key fields | Description |
|------|-----------|-------------|
| `phase_start` | `phase`, `description`, `total` | A pipeline phase began |
| `phase_done` | `phase`, `summary` (object), `total`, `completed` | A phase finished |
| `progress` | `phase`, `current`, `total` | Progress within a phase (driven by `advance_screening`) |
| `api_call` | `source`, `status`, `phase`, `call_type`, `model`, `paper_id`, `latency_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `records`, `details`, `section_name`, `word_count` | One LLM call completed |
| `connector_result` | `name`, `status`, `records`, `error` | One search database returned results |
| `screening_decision` | `paper_id`, `stage`, `decision` | One paper screened |
| `extraction_paper` | `paper_id`, `design`, `rob_judgment` | One paper extracted |
| `synthesis` | `feasible`, `groups` (int count), `n_studies`, `direction` | Meta-analysis summary |
| `rate_limit_wait` | `tier`, `slots_used`, `limit` | Rate limiter pausing |
| `db_ready` | (none) | Run database is open; DB Explorer tabs unlock immediately |
| `done` | `outputs` (object: label -> path), `ts?` | Workflow finished successfully |
| `error` | `msg`, `ts?` | Workflow failed with an error message |
| `cancelled` | `ts?` | Workflow was cancelled by the user |

`heartbeat` events are sent by the backend every 15 seconds of inactivity; `useSSEStream` silently ignores them.

Cost tracking uses `api_call` events exclusively. The `useCostStats` hook only reads events where `type === "api_call"` and `status === "success"`.

---

## 11. Database Schema Reference (for DB Explorer)

The DB Explorer reads from the per-run `runtime.db` (SQLite). Key tables:

| Table | Key columns | Used in |
|-------|------------|---------|
| `papers` | `paper_id`, `title`, `authors`, `year`, `source_database`, `doi`, `abstract`, `country` | Papers tab |
| `screening_decisions` | `paper_id`, `stage`, `decision`, `rationale`, `created_at` | Screening tab |
| `cost_records` | `model`, `phase`, `tokens_in`, `tokens_out`, `cost_usd`, `latency_ms` | Cost Records tab |
| `workflows` | `workflow_id`, `topic`, `config_hash`, `status` | (internal) |

The central registry at `logs/workflows_registry.db` has one table: `workflows_registry` with columns `workflow_id`, `topic`, `config_hash`, `db_path`, `status`, `created_at`, `updated_at`. This is read by `GET /api/history`.
