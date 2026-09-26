# 06 - Keeping Runs Alive Across API Restarts: Options and Recommendation

Question: is a separate worker process actually necessary, or are there cheaper ways to stop
`pm2 restart litreview-api` from killing in-flight workflows?

Snapshot date: 2026-09-26. Line numbers refer to the working tree on that date. Builds on
[01-orchestration-persistence.md](01-orchestration-persistence.md) section 3.1 / F5 and the
P3/P4 phases in [README.md](README.md).

---

## 0. Answer

**A long-lived PM2 worker is not necessary, but some process other than the API must own each
run.** Graceful shutdown, restart guards, and job frameworks cannot fix the dominant failure,
which is restarting on every code edit while a multi-hour run is in progress:

- Graceful shutdown (c) cannot finish a phase inside a 45 s `kill_timeout`, and auto-resume is
  unfaithful until P3 lands.
- Restart guards (d) block the edit-restart-verify loop the project rules require. They also do
  nothing about crashes or `max_memory_restart`.
- A PM2 worker (a) moves the problem rather than removing it. The worker must restart to pick up
  orchestration code, which kills the same runs.
- Job frameworks (e) that work without Redis reduce to huey's `SqliteHuey`. It has the same
  "consumer restart kills running tasks" property and adds nothing the lease table below does not
  already provide.

**Recommended minimal robust option: one detached OS process per run (option b), launched by the
API, tracked by a lease plus heartbeat in the registry, with SQLite `event_log` as the only event
channel.** Each run keeps the code it started with. Restarting the API costs nothing, and new runs
pick up new code. This covers about 80% of P4's intent at about half its cost. It can later grow
into a supervised worker by moving the launcher, without changing the lease or event design.

Stage it:

| Stage | What | Depends on | Effort |
|---|---|---|---|
| 0 | `ops_pm2.sh restart` warns about or refuses live runs; uvicorn `--timeout-graceful-shutdown` | nothing | hours |
| 1 | Per-run detached runner process + registry lease/heartbeat + DB-tailing SSE + CLI lease | nothing (P3 not required) | 2-3 days |
| 2 | Auto-resume runs with a dead lease (crash, reboot, OOM only) | **P3** faithful resume; API keys available without the UI | 1 day after P3 |

---

## 1. How runs live and die today (evidence)

### 1.1 Execution

- `POST /api/run` (and the two CSV variants) call `asyncio.create_task(_run_wrapper(...))`
  inside the uvicorn event loop (`src/web/routers/run_lifecycle.py:170-172, 265-267, 362-364`).
  Resume does the same through `RunLifecycleCoordinator.start_resume`
  (`src/web/lifecycle_coordinator.py:278-282`).
- The run record `_RunRecord` is purely in memory (`src/web/state.py:113-129`). `run_id` is a
  random 8-character id that only this process knows (`run_lifecycle.py:154`).
- Concurrency uses an in-process `asyncio.Semaphore(max_concurrent_runs=2)`
  (`src/web/run_concurrency.py`, `config/settings.yaml:327`). It is invisible to the CLI.
- API keys typed in the UI reach the run only as in-memory `env_overrides`
  (`src/config/env_context.py:54+`, `state.py:474-475`). **They are never persisted.** This
  matters for any auto-resume design.

### 1.2 What `pm2 restart litreview-api` does

1. PM2 sends `SIGINT` by default (`PM2_KILL_SIGNAL`). It sends `SIGKILL` after `kill_timeout`,
   which is 45000 ms for the API (`ecosystem.config.js:25-28`; confirmed live with `pm2 jlist`).
   [PM2 graceful shutdown docs](https://pm2.io/docs/runtime/best-practices/graceful-shutdown/)
2. uvicorn's `handle_exit` sets `should_exit`. `Server.shutdown()` stops accepting connections
   and waits for open connections and **request** tasks to finish, bounded by
   `timeout_graceful_shutdown`. Only then does it send lifespan shutdown
   ([uvicorn `server.py`](https://github.com/encode/uvicorn/blob/master/uvicorn/server.py),
   [settings](https://uvicorn.dev/settings/)). Our PM2 args set no timeout
   (`ecosystem.config.js:35`), so a long-lived SSE connection that does not close can use up
   the 45 s. In that case `SIGKILL` arrives before the lifespan code runs at all.
3. If lifespan shutdown does run, it cancels every workflow task, writes
   `workflows.status='interrupted'`, and waits up to 30 s (`src/web/app.py:97-124`).
   Cancellation raises `CancelledError` at the next `await`. Only two sites in orchestration
   handle it (`runners/writing/post_assembly.py:637, 806`), so in-flight LLM calls are dropped.
   The provider bills those tokens, but the `cost_records` row is written after the response, so
   those calls are most likely never recorded.
4. On startup, the API marks every `running` registry row `interrupted`. It does this blindly,
   using a hard-coded `runs/` path, with no auto-resume (`app.py:77-87`). **This sweep would also
   wrongly mark runs owned by any other live process (for example a CLI run) as interrupted.**

`uvicorn --reload` is not used under PM2, but the module docstring recommends it for dev
(`app.py:3-4`). Under `--reload`, every file save is a restart that kills runs.

### 1.3 How events reach the frontend

- Phases emit through `WebRunContext._emit` into `on_event`, which appends to
  `record.event_log`, an in-memory list (`src/orchestration/context.py:635-652`,
  `src/web/event_store.py:128-145`).
- `EventStore` persists to the runtime DB `event_log` table. "Durable" types (`phase_start`,
  `phase_done`, terminal events) are flushed right away. Everything else is flushed every 5 s
  (`event_store.py:18-28`, `state.py:352-359`).
- `GET /api/stream/{run_id}` serves **only** the in-memory list and returns 404 for unknown run
  ids (`run_lifecycle.py:369-406`). SSE ids are list indexes, so they are not stable across
  processes.
- After a restart the frontend gets a 404, replays `event_log` from SQLite, and marks the run
  `"done"` (`frontend/src/hooks/useSSEStream.ts:250-274`). This is wrong for a run that is still
  alive elsewhere.
- The CLI `RunContext` does not write `event_log` live. It backfills only after a clean exit
  (`src/main.py:346, 460-462`).

Implication: any out-of-process runner requires (1) the runner to write `event_log` directly and
(2) SSE to tail `event_log` by `workflow_id`. This work is identical for options (a) and (b).

### 1.4 Concurrent writers

- `try_claim_for_resume` performs a status-based compare-and-set on the registry
  (`src/db/workflow_registry.py:113-190`). Only the web coordinator calls it
  (`lifecycle_coordinator.py:242`).
- CLI `resume --no-api` and `run` never claim (`main.py:505-525`). By default, CLI `resume`
  delegates to the API (`main.py:478-503`), so the double-writer risk comes from `--no-api` and
  `run`.

---

## 2. What a mid-run kill costs

| Phase | Durable granularity | Lost on kill | Redo cost on resume |
|---|---|---|---|
| Search | per connector (DELETE+INSERT) | everything; no skip | re-queries all connectors; result set can differ; Scopus enrichment lost (01 §2.4) |
| Screening | per paper decision | up to `concurrency` (5) in-flight dual-review calls | small (cents); batch counters wrong on resume (01 F2) |
| Extraction/RoB | per paper | about 4 in-flight papers | small; `excluded_non_primary_count` undercounts (F2) |
| Embedding | per paper, but partial rows count as done | partial/zero vectors kept forever (F3) | silent corruption, not cost |
| Writing | per section draft | sections in flight (3 concurrent, multi-call each) | moderate; RAG counters lost (F2) |
| Finalize | files + split-brain window (F9) | registry may say `completed` too early | manual repair |

The direct dollar cost of a single kill is small. **The real costs are resume
unfaithfulness (F2/F3) and hours of wall-clock time**, and both are paid on every restart. That
is why "auto-resume after every restart" (option c) is dangerous before P3, and why avoiding the
kill beats recovering from it.

---

## 3. Options evaluated

### (a) Dedicated PM2 worker + SQLite run queue + leases/heartbeats

- API inserts `run_requests`; a `litreview-worker` process claims them with a lease, runs up to N
  runs in its own event loop, heartbeats, and writes `event_log`. API SSE tails the DB.
- **Pros:** PM2 supervises it and restarts it after a crash. One process gives one shared rate
  limiter and one concurrency count. It is a conventional design.
- **Cons:** The worker has to be restarted for `src/orchestration`, `src/llm`, and other edits
  to take effect, and **that kills every run it hosts, exactly like today.** Surviving that needs
  a drain mode, but runs last hours, so in practice people will restart anyway or wait. It adds a
  queue table, a polling loop, a second PM2 app, and changes to the ops scripts and rules. A
  worker crash also takes down all runs together.
- **Verdict:** Fixes API-only restarts, which are rare for backend work, but not worker restarts,
  which are frequent. Over-built for `max_concurrent_runs=2` on one machine.

### (b) Detached subprocess per run, owned by the API, surviving API restarts

- API spawns `python -m src.worker.run_process --workflow-id ... --mode fresh|resume` per run.
  The child acquires the registry lease, heartbeats, writes `event_log`, and exits when the run
  ends.
- **Pros:**
  - **Each run pins the code it started with.** Restarting the API never touches runs, and new
    runs use new code. This matches the project's edit, restart, rerun loop exactly.
  - A crash affects one run, not all of them.
  - No queue and no polling worker. Provider credentials go to the child through the process
    environment only, so they are never stored.
  - It reuses the existing CLI resume path (`run_workflow`, `run_workflow_resume`).
- **Cons / gotchas (all solvable):**
  - PM2 `treekill` defaults to **true**, meaning "kill the whole tree, not just the main process"
    ([ecosystem reference](https://pm2.io/docs/runtime/reference/ecosystem-file/)). It has been
    reported to kill children even when they were spawned `detached`
    ([pm2#3292](https://github.com/Unitech/pm2/issues/3292)). Fix: `treekill: false` on
    `litreview-api` plus `start_new_session=True`, or double-fork so the child is re-parented
    to launchd.
  - Do **not** use `asyncio.create_subprocess_exec`. Closing its transport (on loop shutdown or
    GC) calls `proc.kill()` on a running child (CPython `asyncio/base_subprocess.py:99-121`).
    Use `subprocess.Popen` plus a non-blocking reaper instead.
  - PID reuse: validate the lease token and heartbeat freshness, not just the PID, before
    signalling.
  - There is no supervisor. A machine reboot or OOM kills the child, and the dead lease is
    detected by the API (Stage 2 handles auto-resume).
  - Rate limiter is per process (01 §3.3). With 2 runs this is 2 limiters on one key, the same as
    today's CLI+API case. Acceptable until P8 (SQLite token bucket).
  - Lazily imported modules can load newer code mid-run if files change on disk. The API process
    has the same issue today. Mitigate by eagerly importing `src.orchestration.workflow` and the
    runners at child startup, and by recording `code_rev` (git SHA) on the lease row.
- **Verdict: recommended.** It solves the actual failure with the least machinery.

### (c) Graceful shutdown: kill_timeout + SIGTERM handler that checkpoints, then auto-resume

- Phases run for minutes to hours; nothing completes in 45 s. The best a handler can do is
  "stop dispatching new papers, await in-flight calls, commit". Screening and extraction already
  persist per paper, so this saves at most about 5-10 in-flight calls (cents).
- Auto-resume on startup brings back F2 (wrong Methods/PRISMA numbers), F3 (zero vectors kept),
  search re-querying, and duplicate writing calls **on every restart**. Runs started with
  UI-supplied API keys cannot be auto-resumed at all, because the keys are not persisted (§1.1).
- **Verdict:** Worth doing only as crash recovery (Stage 2) after P3. It is not a restart
  strategy. The cheap part is still worth taking now: set `--timeout-graceful-shutdown 10` so SSE
  connections cannot eat the 45 s window and skip lifespan cleanup.

### (d) Avoid hot reload; restart only when idle; `ops_pm2.sh restart` refuses when runs are active

- It takes about 30 lines: query the registry for `status='running'` rows with a fresh
  `heartbeat_at`, then refuse unless `--force`, or wait.
- **Pros:** Immediate, and it stops agents from casually killing runs.
- **Cons:** It blocks the rule-mandated "restart after every `src/` change" loop for hours, and
  agents will learn to pass `--force`. It does nothing for PM2 autorestart after a crash,
  `max_memory_restart: 2G` (workflows count against the API's memory today), a raw
  `pm2 restart`, or machine sleep and reboot.
- **Verdict:** Stage 0 guardrail only. Once (b) lands it becomes a warning, because API restarts
  are then safe.

### (e) Job frameworks without Redis

| Framework | Backends | Fits SQLite + no Redis? | Notes |
|---|---|---|---|
| huey | Redis, **SqliteHuey**, Postgres, File | **Yes** ([huey storage docs](https://huey.readthedocs.io/en/latest/guide.html)) | Tasks are sync functions, so each would need `asyncio.run`; revoke only stops pending tasks; restarting the consumer kills running tasks |
| procrastinate | PostgreSQL only | No | Would need a Postgres server |
| arq | Redis only | No | asyncio-native, but requires Redis |
| dramatiq | RabbitMQ / Redis | No | [reference](https://dramatiq.io/reference.html) |
| saq | Redis / Postgres | No | |

- **Verdict:** Only huey fits, and it amounts to option (a) with a third-party queue schema. It
  does not know about our registry, per-workflow exclusivity, `event_log`/SSE, or cancellation of
  a running multi-hour task. A 3-column lease on `workflows_registry` is smaller and
  domain-correct. Not recommended.

### Summary

| Option | Survives API restart | Survives code-edit restart | Survives crash/OOM | Needs P3 | Effort |
|---|---|---|---|---|---|
| (a) PM2 worker | yes | **no** (worker restart) | resume only | for auto-resume | M-L |
| (b) per-run process | **yes** | **yes** | resume only | for auto-resume | M |
| (c) graceful + auto-resume | no (resumes) | no (resumes) | resume only | **yes** | M |
| (d) restart guard | by refusing | by refusing | no | no | S |
| (e) huey | = (a) | no | resume only | for auto-resume | M |

---

## 4. Recommended design

### Stage 0 - guardrails (now, hours)

- `scripts/ops_pm2.sh restart` checks for live runs before restarting `litreview-api` (backend,
  `--prod-ui`, `--all`). Live means registry `status='running'` with `heartbeat_at` newer than
  2x the heartbeat interval. The script prints the list and exits 1 unless `--force`. Do the
  registry query through a helper (for example a `scripts/check.py active-runs` subcommand),
  following the scripts rule.
- `ecosystem.config.js`: add `--timeout-graceful-shutdown 10` to the uvicorn args.
- Update `app.py` docstring: `--reload` kills runs; do not use it while runs are active.

### Stage 1 - per-run runner process (P4-lite, 2-3 days, independent of P3)

**Lease (registry is the lease authority; the runtime DB stays the status authority per R5):**

```sql
ALTER TABLE workflows_registry ADD COLUMN lease_token TEXT;
ALTER TABLE workflows_registry ADD COLUMN lease_expires_at TEXT;
ALTER TABLE workflows_registry ADD COLUMN runner_pid INTEGER;
ALTER TABLE workflows_registry ADD COLUMN code_rev TEXT;
CREATE TABLE IF NOT EXISTS run_attempts (          -- stable run_id across API restarts
    run_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, mode TEXT NOT NULL,
    pid INTEGER, started_at TEXT, ended_at TEXT, exit_status TEXT);
```

```python
# src/orchestration/run_lease.py
async def acquire(run_root, workflow_id, *, ttl_s=90) -> str | None:
    token = uuid4().hex
    # single UPDATE: claim if resumable/draft status OR lease expired; returns rowcount
    ...  # UPDATE ... SET status='running', lease_token=?, lease_expires_at=now+ttl,
         #   runner_pid=?, code_rev=? WHERE workflow_id=? AND (lease_token IS NULL
         #   OR lease_expires_at < datetime('now'))
    return token if changed else None

async def renew(run_root, workflow_id, token, ttl_s=90) -> bool: ...   # WHERE lease_token=?
async def release(run_root, workflow_id, token, status) -> None: ...   # clears lease
```

- `try_claim_for_resume` becomes a thin wrapper over `acquire`.
- **CLI `run` / `resume --no-api` must call `acquire`** and refuse with exit 1 if it returns
  `None`. This fixes the CLI/API double-writer problem.

**Runner entrypoint** `src/worker/run_process.py` (`python -m src.worker.run_process`):

```python
async def main(args):
    eager_import_pipeline()                       # pin code at spawn
    token = await run_lease.acquire(args.run_root, args.workflow_id)
    if token is None: sys.exit(3)                 # someone else owns it
    ctx = DbRunContext(db_path_resolver, workflow_id, flush_interval_s=1.0)  # writes event_log
    hb = asyncio.create_task(renew_loop(token))   # every 30s; on False -> cancel run (lost lease)
    main_task = asyncio.current_task()
    loop.add_signal_handler(SIGTERM, main_task.cancel)   # user cancel
    try:
        result = await (run_workflow(..., workflow_id=args.workflow_id, fresh=True)
                        if args.mode == "fresh" else
                        run_workflow_resume(workflow_id=args.workflow_id, from_phase=args.from_phase, ...))
        await apply_terminal_status(result)      # reuse state._apply_terminal_registry_status logic
    except asyncio.CancelledError:
        ctx.emit_terminal("cancelled"); status = "interrupted"
    finally:
        await ctx.flush(); hb.cancel(); await run_lease.release(..., token, status)
```

- `DbRunContext` is `WebRunContext` with `on_event` bound to an `EventStore` write path. It
  writes durable types immediately and batches the rest every 1 s, so the loss window drops from
  5 s to 1 s. It emits `workflow_id_ready` / `db_ready` exactly as today.
- Fresh runs: the API calls `allocate_workflow_id` and creates a draft registry row
  (`config_ready`) before spawning. `start_runner.py:38-45` already adopts a reserved draft id,
  so the child knows its `workflow_id` from the start and there is no handshake race.

**Launcher** `src/web/run_launcher.py` (replaces task creation in `_run_wrapper` /
`start_resume`):

```python
def spawn(run_id, workflow_id, mode, review_path, run_root, env_overrides, from_phase=None) -> int:
    log = open(run_dir / f"runner_{run_id}.log", "ab")
    proc = subprocess.Popen(
        [sys.executable, "-m", "src.worker.run_process", "--workflow-id", workflow_id,
         "--mode", mode, "--run-id", run_id, "--review-path", review_path, "--run-root", run_root,
         *(["--from-phase", from_phase] if from_phase else [])],
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True, close_fds=True, cwd=PROJECT_DIR)
    _children[proc.pid] = proc                      # reaped by a 5s poll loop (proc.poll())
    return proc.pid
```

- Concurrency: `acquire_run_slot_or_raise` counts registry rows with a live lease instead of
  `semaphore._value`. This gives the same 429 behaviour, now correct across processes and API
  restarts.
- Cancel: `POST /api/cancel/{run_id}` looks up `run_attempts` → `workflow_id` → registry
  (`runner_pid`, `lease_token`, fresh `lease_expires_at`) and then calls `os.kill(pid, SIGTERM)`.
  If the lease is stale, it returns 409 or marks the run interrupted.
- Keep the old in-process path behind `settings.web.run_executor: subprocess | inprocess`, for
  tests and rollback.

**SSE from the database (the only event channel):**

- `GET /api/stream/{run_id}`: resolve `run_id` through `run_attempts` (persisted, so it survives
  API restarts), then tail `event_log WHERE workflow_id=? AND id > ?`.
  - Use the SQLite row `id` as the SSE `id`. `Last-Event-ID` then works across API restarts.
  - Poll every 0.5-1 s using the existing read-only `open_runtime_db`.
  - End the stream on a `done` / `error` / `cancelled` event, or when the lease is dead and no
    terminal event arrives within a grace period (emit `error: runner lost`).
- `GET /api/stream/workflow/{workflow_id}`: announce from `run_attempts` rows with a live lease
  instead of the in-memory broadcaster.
- Frontend (`useSSEStream.ts:250-274`): after this change a 404 means the run id is truly
  unknown. The replay fallback should set status from the terminal event it finds, not always
  `"done"`. No other frontend change is needed, because endpoint shapes are unchanged
  (endpoint parity preserved).

**Startup and PM2:**

- `app.py` lifespan: replace the blanket `running → interrupted` sweep (`:77-87`) with lease
  reconciliation. Rows with an expired lease and a dead PID become `interrupted`; live leases
  are left alone. Remove the task-cancel loop for subprocess runs, because the API no longer
  owns them. Use the configured run root instead of the hard-coded `runs/`.
- `ecosystem.config.js`: `treekill: false` on `litreview-api` (belt) + `start_new_session`
  (braces).
- `ops_pm2.sh`: with `run_executor=subprocess`, the Stage 0 guard becomes a warning that lists
  live runs and their `code_rev`.

### Stage 2 - auto-resume after crash/reboot/OOM (after P3)

- A reconciler, run at API startup and every 60 s, finds `status='running'` rows whose lease has
  expired and whose PID is dead. It records a `workflow_steps` failure with category `transient`
  and, subject to a `recovery_policies` bound (for example 2 auto-resumes per workflow), spawns
  `--mode resume`.
- Preconditions:
  - **P3 landed:** `phase_outputs` hydrate state, settings snapshot, nodes skip completed
    checkpoints, and F3 is fixed.
  - The required provider credentials resolve from the operator process env. Otherwise mark the run
    `awaiting_user_action`, because UI keys are not stored.
  - The run's `code_rev` is compatible, or a policy allows resuming on new code.
- Add a resume-equivalence test (R6) that kills the runner at each phase boundary and during
  screening, then asserts that the resumed `phase_outputs` equal a straight-through run.

### Do we still want a PM2 worker later?

Only if you need (1) automatic restart of a crashed runner without the API being up, or (2)
more than about 3 concurrent runs sharing one rate limiter. Either way, move `run_launcher` into
a small `litreview-supervisor` PM2 app that still spawns one process per run. The lease table,
`DbRunContext`, and DB-tailing SSE stay unchanged, so Stage 1 is not throwaway work.
**Recommend amending README P4** from "dedicated PM2 worker" to "per-run runner process + lease;
supervisor optional".

---

## 5. File list

| File | Change | Stage |
|---|---|---|
| `scripts/ops_pm2.sh` | live-run guard / warning, `--force` | 0 |
| `scripts/check.py` | `active-runs` subcommand (JSON list of live leases) | 0 |
| `ecosystem.config.js` (+ `ecosystem.config.example.js`) | `--timeout-graceful-shutdown 10`; `treekill: false` on api | 0 / 1 |
| `src/web/app.py` | docstring (`--reload`); lease-based startup reconciliation; drop task-cancel for subprocess runs; configured run root | 0 / 1 |
| `src/db/workflow_registry.py` | lease columns migration, `run_attempts` table; `try_claim_for_resume` → wrapper | 1 |
| `src/orchestration/run_lease.py` (new) | `acquire` / `renew` / `release` | 1 |
| `src/worker/__init__.py`, `src/worker/run_process.py` (new) | runner entrypoint, SIGTERM handling, heartbeat, eager imports | 1 |
| `src/orchestration/context.py` | `DbRunContext` (WebRunContext + direct event_log sink) | 1 |
| `src/web/event_store.py` | direct-write helper; `tail(db_path, workflow_id, after_id)` | 1 |
| `src/web/run_launcher.py` (new) | `Popen` spawn, reaper, cancel-by-lease | 1 |
| `src/web/state.py` | `_run_wrapper` / `_resume_wrapper` → launcher when `run_executor=subprocess` | 1 |
| `src/web/run_concurrency.py` | count live leases instead of semaphore | 1 |
| `src/web/lifecycle_coordinator.py` | `start_resume` / attach use `run_attempts` + launcher | 1 |
| `src/web/routers/run_lifecycle.py` | start/stream/cancel via `run_attempts` + DB tail | 1 |
| `src/main.py` | CLI `run` / `resume --no-api` acquire lease | 1 |
| `src/config/` settings model + `config/settings.yaml` | `web.run_executor`, `lease_ttl_seconds` | 1 |
| `frontend/src/hooks/useSSEStream.ts` | replay fallback derives status from terminal event | 1 |
| `src/web/lifecycle_reconciler.py` | dead-lease detection; Stage 2 auto-resume policy | 1 / 2 |
| `tests/unit/test_run_lease.py`, `tests/integration/test_run_process_survives_api_restart.py`, `tests/unit/test_sse_db_tail.py`, `tests/unit/test_cli_lease_exclusion.py` | new | 1 |
| `tests/integration/test_resume_equivalence.py` | kill-at-boundary equivalence (R6) | 2 |
| `docs/ARCHITECTURE.md`, `docs/SCRIPTS.md`, `scripts/help.sh`, `.cursor/rules/core/pm2-restart.mdc`, `.cursor/rules/core/gotchas.mdc`, `docs/rearchitecture/README.md` (P4 wording) | docs | 0-2 |

Key Stage 1 test: start a stub-LLM run in subprocess mode, `SIGINT` the API process (simulating
the PM2 restart), start a new API, and assert that:

- the runner PID is still alive;
- `/api/stream/{run_id}` resumes from `Last-Event-ID`;
- the run reaches `done`;
- a concurrent CLI `resume --no-api` exits non-zero because it cannot acquire the lease.
