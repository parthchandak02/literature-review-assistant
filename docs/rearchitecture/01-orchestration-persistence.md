# 01 - Orchestration and Persistence: Architecture Map and Robustness Critique

Scope: `src/orchestration/**`, `src/db/**`, `src/models/workflow.py`, `src/models/enums.py`,
`src/main.py`, `src/config/**`, `config/*.yaml`, with supporting reads of `src/web/state.py`,
`src/web/event_store.py`, `src/web/app.py`, `src/llm/shared_rate_limiter.py`, `src/rag/embedder.py`.
Claimed design read from `docs/ARCHITECTURE.md`, `docs/CONTEXT.md`, `.cursor/rules/core/gotchas.mdc`.

Snapshot date: 2026-09-26 (HEAD `8adceb5`). Line numbers refer to that tree.

---

## 0. Executive summary

The pipeline is a linear `pydantic_graph` of 14 node classes (`src/orchestration/workflow.py:314-334`)
that share one mutable `ReviewState` dataclass (`src/orchestration/state.py:16-77`). Durable truth
lives in a per-run SQLite `runtime.db` (43 tables) plus a central `runs/workflows_registry.db`.
Resume is checkpoint-marker based: `checkpoints(workflow_id, phase, status)` decides the first phase
to re-enter, and each phase is expected to skip already-persisted per-paper rows.

The design intent is sound (DB-first, typed contracts, per-paper idempotency, step journal,
bounded recovery). The implementation has four systemic weaknesses:

1. **In-memory state is load-bearing but not durable.** About 15 `ReviewState` fields that feed the
   manuscript Methods section and PRISMA/PROSPERO outputs are set only in memory and never restored on
   resume. A resumed run silently writes different (wrong) numbers than a straight-through run.
2. **The control plane is mostly decorative.** `workflow_steps`, `recovery_policies`,
   `FailureCategory`, and `RecoveryAction` are recorded, but only the pre-writing gate reads them to
   make a decision, and that decision's bound is defeated by its own rollback (unbounded rewind loop).
   There is no retry executor, no input/output hashing, and three gates (cost budget, resume integrity,
   citation lineage) are defined but never called.
3. **Workflows run inside the API process.** `pm2 restart litreview-api` (which project rules require
   after every backend edit) kills every in-flight run; startup just marks them `interrupted`.
   Two independent stores (registry vs runtime.db) are updated without ordering guarantees, producing
   split-brain status.
4. **Failure is swallowed by default.** 90+ `except Exception` sites in scope, 21 of them `pass`.
   Several convert hard failures into silent data corruption (zero-vector embeddings, dropped papers,
   lost cost records), which downstream gates then accept as valid.

The ranked recommendations in section 5 focus on: a durable, typed `PhaseOutput` per phase that
replaces in-memory state; a single phase-runner harness that owns journaling, checkpointing,
retry and rollback; a separate worker process with a DB lease; and golden replay tests that
compare resumed runs against straight-through runs.

---

## 1. Phase graph

### 1.1 Graph definition and routing

- Graph: `RUN_GRAPH = Graph(nodes=[StartNode, ResumeStartNode, ProsperoGateNode, SearchNode,
  ScreeningNode, HumanReviewCheckpointNode, ExtractionQualityNode, EmbeddingNode, SynthesisNode,
  KnowledgeGraphNode, PreWritingGateNode, WritingNode, ManuscriptAuditNode, FinalizeNode],
  state_type=ReviewState, run_end_type=WorkflowRunResult)` (`workflow.py:314-334`).
- Every node in `src/orchestration/nodes/*.py` is a 15-25 line shim that calls a runner in
  `src/orchestration/runners/*.py` and returns the next node or `End(WorkflowRunResult)`.
  Exceptions: `EmbeddingNode` (`embedding_node.py`, logic inline) and `KnowledgeGraphNode`
  (`knowledge_graph_node.py`, logic inline) live at the package root, not under `nodes/`.
- Canonical phase keys: `PHASE_ORDER` (`phase_catalog.py:5-17`). Sub-phase checkpoints:
  `SUB_PHASE_CHECKPOINTS` (`phase_catalog.py:49-60`) - `phase_3b_fulltext`, `phase_6a_hyde`,
  `phase_6a2_outline`, `phase_6b_phase_a`, `phase_6c_phase_b`, `phase_6d_assembly`,
  `phase_6e_concepts`, `phase_6f_custom_diagrams`.
- Fresh entry: `run_workflow` -> `StartNode` (`workflow.py:428-500`).
- Resume entry: `run_workflow_resume` -> `load_resume_state` -> `ResumeStartNode`
  (`workflow.py:354-407`), which maps a phase string to a node via an `if` ladder
  (`nodes/resume_start.py:63-87`; unknown strings fall through to `SearchNode`).

Important routing property: **after the entry node, every downstream node runs unconditionally.**
No node checks whether its own checkpoint is already `completed`. Correctness on resume therefore
depends on every phase being internally idempotent.

### 1.2 Phase table

| # | Node / checkpoint key | Reads (state / DB) | Writes (DB / files / state) | Gate / exit |
|---|---|---|---|---|
| 0 | `StartNode` / none (`runners/start_runner.py:28-130`) | review + settings YAML | `workflows` row, registry row, `config_snapshot.yaml`, `review.yaml`; sets `workflow_id`, `db_path`, `artifacts` | none |
| 1 | `ProsperoGateNode` / `phase_1_prospero_gate` (`runners/prospero_gate_runner.py:64-160`) | `state.review.protocol` | pre-registration artifacts, `run_summary.json` stub, registry `awaiting_prospero`, checkpoint | Web: `End(awaiting_prospero)`. CLI: polls registry forever (`:139-143`, no timeout) |
| 2 | `SearchNode` / `phase_2_search` (`runners/search_runner.py:78-449`) | connectors, optional CSVs, parent DB | `search_results`, `papers`, `workflows.dedup_count`, `gate_results`, `doc_protocol.md`; state `deduped_papers`, `dedup_count`, `search_counts`, `search_queries`, `connector_init_failures` | `search_volume` gate; strict + FAILED -> `End(failed)` |
| 3 | `ScreeningNode` / `phase_3_screening` (+`phase_3b_fulltext`) (`runners/screening_runner.py:83-1243`) | `state.deduped_papers`, prior `screening_decisions` | `screening_decisions`, `dual_screening_results`, `study_cohort_membership`, `decision_log` metrics, PDFs under `papers/`; state `included_papers`, kappa, ~10 batch/fulltext counters, `sparse_evidence_mode` | `screening_safeguard` gate; strict + FAILED -> `End(failed)`; checkpoint `partial` on Ctrl+C |
| 3h | `HumanReviewCheckpointNode` / none (`runners/hitl_runner.py:25-101`) | settings `human_in_the_loop` | registry `awaiting_review` | Web: `End(awaiting_review)`; CLI: poll up to `max_wait_seconds` |
| 4 | `ExtractionQualityNode` / `phase_4_extraction_quality` (`runners/extraction_runner.py:136-1099`) | canonical included IDs, prior `extraction_records`, `rob_assessments` | `extraction_records`, RoB2/ROBINS-I/CASP/MMAT/GRADE tables, cohort membership, `decision_log`, `fig_rob_traffic_light.png`; state `extraction_records`, `included_papers` (filtered), `excluded_non_primary_count`, `heuristic_assessment_count` | `extraction_completeness` gate; strict + FAILED -> `End(failed)` |
| 4b | `EmbeddingNode` / `phase_4b_embedding` (`embedding_node.py:28-181`) | `state.extraction_records`, `paper_chunks_meta` paper IDs | `paper_chunks_meta` (`INSERT OR IGNORE`), `cost_records` | none |
| 5 | `SynthesisNode` / `phase_5_synthesis` (`runners/synthesis_runner.py`) | `state.extraction_records`, `state.sparse_evidence_mode` | `synthesis_results` (upsert), forest/funnel figures, `decision_log` | none |
| 5b | `KnowledgeGraphNode` / `phase_5b_knowledge_graph` (`knowledge_graph_node.py`) | `state.extraction_records` | `paper_relationships`, `graph_communities`, `research_gaps` (all `INSERT OR IGNORE`), evidence network figure | none |
| 5c | `PreWritingGateNode` / `phase_5c_pre_writing_gate` (`runners/pre_writing_gate_runner.py:29-165`, `helpers/pre_writing_gate.py`) | cohort, extraction, quality, chunk IDs, PRISMA counts | `validation_runs`, `validation_checks`, `recovery_policies`, `workflow_steps`, checkpoint `completed`/`blocked` | Deterministic checks; rewind to 4/4b/5/5b or `raise RuntimeError` |
| 6 | `WritingNode` / `phase_6_writing` (`runners/writing_runner.py`, `runners/writing/*.py`) | `run_writing_setup` builds grounding from state + DB | `section_drafts`, `section_outlines`, `manuscript_*`, `claims`/`citations`/`evidence_links`, `writing_manifests`, `fallback_events`, `doc_manuscript.md` | Section persistence invariant -> `RuntimeError` |
| 7 | `ManuscriptAuditNode` / `phase_7_audit` (`runners/audit_runner.py`) | `doc_manuscript.md`, citation DB | `manuscript_audit_runs/findings`, `.tex` refresh | `audit_gate_mode` blocking -> `End(gate_blocked)`; missing manuscript -> `End(failed)` |
| F | `FinalizeNode` / `finalize` (`runners/finalize_runner.py:35-299`) | state, cohort, manifest, cost | `run_summary.json`, LaTeX/bib, PROSPERO docx, `submission/`, registry + runtime status | Errors -> `status=failed`, checkpoint `blocked` |

### 1.3 Typed contracts at boundaries (claimed vs actual)

The claim (`AGENTS.md`, `overview.mdc`): "No untyped dicts across phase boundaries."
Actual boundary is `ReviewState`, a `@dataclass` (not Pydantic, no validation) with:

- `dict[str, str]` `artifacts` (file-path bag used as an implicit registry by every phase),
  `dict[str, int]` `search_counts`, `dict[str, str]` `search_queries`, `dict[str, str]`
  `connector_init_failures` (`state.py:28-35`).
- About 20 scalar counters added ad hoc for manuscript grounding (`state.py:36-77`).
- `run_writing_setup` returns an untyped `dict` consumed by `writing_runner.py:124-146`
  (`runners/writing/setup.py:350-359`).
- Four runners are annotated `-> End[dict] | None` while returning `End[WorkflowRunResult]`
  (search, screening, extraction, audit).
- `WorkflowRunResult.details: dict[str, Any]` (`models/workflow.py:40`), and
  `from_summary` defaults any unrecognized status to `COMPLETED` (`models/workflow.py:84-85`) -
  a fail-open mapping.
- All SSE / `event_log` events are free-form `dict[str, Any]` (`context.py:635-652`).

---

## 2. Resume, recovery, and checkpoint model

### 2.1 Stores

| Store | Location | Role | Writers |
|---|---|---|---|
| `workflows_registry` | `runs/workflows_registry.db` (`db/workflow_registry.py:22-60`) | topic/config_hash -> `db_path`, `status`, heartbeat | start, search, prospero, hitl, finalize, audit, web lifecycle |
| `workflows` | runtime.db | per-run status, `dedup_count`, `writing_generation` | start, search, gates, finalize |
| `checkpoints` | runtime.db, PK `(workflow_id, phase)` | phase-completion markers; `completed` never downgrades (`repos/workflow_state.py:31-61`) | each runner at end |
| `workflow_steps` | runtime.db | step journal (`helpers/step_journal.py`) | search, screening, extraction, pre-writing gate, writing, finalize (phase-level only) |
| `recovery_policies` | runtime.db | bounded retry/rewind counters | **pre-writing gate only** |
| `event_log` | runtime.db | activity feed, also used as a data source on resume | web `EventStore` only (`web/event_store.py:46-62`); CLI backfills after a clean exit (`main.py:346`) |
| per-paper tables | runtime.db | actual durable work product | phases |
| file artifacts | run dir | figures, manuscript, PDFs, summary | phases |

### 2.2 Resume algorithm (`orchestration/resume.py:104-295`)

1. `validate_resume_allowed` rejects resume if `finalize` is completed (`:40-65`).
2. Loads review config from workspace, then overrides with run `config_snapshot.yaml` (`:125-134`).
3. `repair_foreign_key_integrity` inserts stub `papers`/`workflows` rows for orphaned references
   (`db/database.py:642-722`).
4. Rebuilds `deduped_papers` by re-running `deduplicate_papers` over **all** rows in `papers`
   (`:148-149`); `included_papers` from fulltext include IDs, falling back to title/abstract.
5. Loads `extraction_records` only if the `phase_4` checkpoint exists (`:163-165`).
6. Restores kappa from the latest `phase_done` payload in `event_log` (`:172-198`).
7. `from_phase`: deletes checkpoints for the cascade plus sub-phases, calls
   `rollback_phase_data`, deletes section drafts (`:200-250`). If a prior checkpoint is missing,
   it silently falls back to the first incomplete phase (`:206-217`).
8. Guard: if writing is checkpointed but `doc_manuscript.md` is missing, clears the writing
   checkpoint (`:253-267`).
9. `ResumeStartNode` then consults the **registry** status; `awaiting_review` / `awaiting_prospero`
   override the checkpoint-derived phase (`runners/start_runner.py:133-148`, exceptions swallowed).

### 2.3 Failure classification and retry

- Enums exist: `StepStatus`, `FailureCategory {transient, repairable, rewindable,
  user_action_required, terminal}`, `RecoveryAction {retry, rewind, skip, user_action, abort}`
  (`models/enums.py:109-130`).
- Actual use (full grep of `src/`):
  - `TERMINAL/ABORT`: extraction gate failure (`extraction_runner.py:1064-1065`), pre-writing gate
    (`pre_writing_gate_runner.py:151-152`).
  - `REWINDABLE/REWIND`: pre-writing gate (`:107-108`).
  - `REPAIRABLE`: writing with failed sections (`writing_runner.py:223`), no action attached.
  - `TRANSIENT`, `RETRY`, `SKIP`, `USER_ACTION`: **never used**.
  - `increment_retry_count` (`repos/workflow_state.py:386-403`): **never called**.
  - `input_hash` / `output_hash` on `workflow_steps`: **never populated** outside the repo layer.
- Transient LLM errors are retried inside `_run_with_retry` (`src/llm/pydantic_client.py:131`),
  invisible to the control plane. Any other exception propagates out of the graph; the web wrapper
  marks the run `failed` (`web/state.py:521-539`). Recovery is always "human clicks resume".

### 2.4 Phase idempotency on resume

| Phase | Mechanism | Verdict |
|---|---|---|
| Start | new `workflow_id` each fresh run; draft reuse | OK |
| PROSPERO | regenerates artifacts every entry | OK (file overwrite) |
| Search | `save_search_result` DELETE+INSERT per database (`repos/papers.py:136-171`); papers upserted; **no skip**: re-running re-queries every connector | Not idempotent in cost/time; result set can differ (live APIs). Scopus abstract enrichment is applied only to in-memory papers after they were persisted (`search_runner.py:393-409`), so enrichment is lost on resume |
| Screening | skips `get_processed_paper_ids(..., "title_abstract")` / `"fulltext"`; `screening_decisions` has a unique index (migration 12) | Mostly OK. Batch pre-ranker counters recomputed only for the unprocessed remainder (`screening_runner.py:617-620`) |
| HITL | registry-status driven | OK, but can re-route a completed run backward if registry status is stale |
| Extraction/quality | skips papers already in `extraction_records` / `rob_assessments` | Per-paper OK; `excluded_non_primary_count` counts only papers processed in this invocation (`:950`), so it undercounts after partial resume |
| Embedding | skips any paper with at least one chunk row | Unsafe: partial or zero-vector chunks are treated as done forever (see F3) |
| Synthesis | upsert on `(workflow_id, outcome_name)` | OK, but stale outcomes from a previous grouping remain |
| Knowledge graph | `INSERT OR IGNORE` | Stale rows survive re-entry without rollback (weights/paper lists not updated) |
| Pre-writing gate | recovery policy | Broken bound (see F1) |
| Writing | `section_drafts` skip + `writing_generation` | Reasonable; checkpoint written before manifests/journal (`writing_runner.py:206-277`) |
| Audit | appends new audit run | OK |
| Finalize | overwrites files | Registry updated before runtime DB (split-brain window, F9) |

---

## 3. Concurrency model

### 3.1 Process topology

- **API process = worker process.** `POST /api/run` creates an `asyncio` task that calls
  `run_workflow` inside the FastAPI event loop (`web/state.py:430-485`); resume likewise
  (`web/state.py:587-608`). There is no separate worker.
- Concurrency cap: in-process `asyncio.Semaphore(settings.web.max_concurrent_runs=2)`
  (`web/run_concurrency.py`), which reads the private `semaphore._value`.
- On shutdown the lifespan cancels tasks and writes `status='interrupted'`
  (`web/app.py:97-113`). On startup it marks every `running` registry row `interrupted`, using a
  hard-coded `runs/` path regardless of the configured run root (`web/app.py:77-87`). No
  auto-resume.
- CLI `run` and `resume --no-api` execute in their own process with their own rate limiter and
  no claim on the workflow (`main.py:433-520`; `run_workflow_resume` never calls
  `try_claim_for_resume`). The CLI and API can therefore run the same `workflow_id` against the same
  runtime.db at the same time.

### 3.2 Within a run

- Phases run sequentially; within a phase, `asyncio.gather` + `Semaphore` fan out LLM work
  (screening 5, extraction 4, embeddings 4, writing 3; `config/settings.yaml`), raised further by
  `execution_profile: throughput` (`config/execution_profiles.py:13-23`).
- **One aiosqlite connection is shared by all concurrent tasks of a phase** (for example,
  extraction opens one `get_db` at `extraction_runner.py:149` and fans out at `:465` and `:920`).
  aiosqlite serializes statements, but the transaction is connection-wide: one task's `commit()`
  commits another task's half-finished multi-statement write, and an error path cannot roll back
  just its own work.
- Side connections are opened while the main phase connection is alive (writing:
  `writing_runner.py:80-102` open new connections for checkpoints while `db` from `:109` is held;
  step-journal writes open more connections). With WAL plus `busy_timeout=5000`
  (`db/database.py:23`), an uncommitted write on the main connection stalls these for up to 5s,
  then raises `database is locked`, which most journal call sites swallow.

### 3.3 Rate limiting

- `get_shared_rate_limiter` keeps one `RateLimiter` per API-key hash per process
  (`llm/shared_rate_limiter.py:21-37`). The `on_waiting` / `on_resolved` callbacks are captured
  **only when the limiter is first created** (`:28-36`), so the second concurrent (or later) web run
  sends its rate-limit events to the first run's `RunContext`, which may already be finished.
- CLI + API processes double the effective RPM against the same key.
- The limiter is a sliding window plus minimum interval (`llm/rate_limiter.py:35-60`). It knows
  nothing about tokens-per-minute or provider-returned `Retry-After` beyond what `_run_with_retry`
  does.

### 3.4 SQLite connection lifecycle

- `get_db` opens a new connection **and runs the full migration pass on every open**
  (`db/database.py:742-753`): `executescript(schema.sql)` (612 lines), a version probe,
  and `_validate_schema_contract` (about 20 `PRAGMA table_info` calls). There are 79 `get_db(`
  call sites in `src/`; many phases open 3-10 connections (for example
  `runners/writing/post_assembly.py` 10, `finalize_runner.py` 7).
- `get_db` has a default path of `data/checkpoints/review_state.db`, so a missing `db_path` quietly
  creates a stray DB instead of failing.
- Two connection factories with different semantics: `get_db` (migrates, no connect timeout) and
  `open_runtime_db` (no migration, connect timeout, read-only option).

---

## 4. Fragility points (evidence)

Severity: **S1** = silent wrong output or unbounded cost; **S2** = failed or stuck run needing a
human; **S3** = maintainability or drift.

### F1 (S1) Pre-writing gate rewind bound is erased by its own rollback -> unbounded rewind loop

- The gate loads a policy with `max_rewinds=1` (`pre_writing_gate_runner.py:46-52`), increments
  `current_rewinds` (`:97-101`), then calls `rewind_pre_writing_phase` (`:110-114`).
- `rewind_pre_writing_phase` -> `rollback_phase_data(workflow_id, rewind_phase)`
  (`helpers/pre_writing_gate.py:232-241`).
- `rollback_phase_data` deletes `recovery_policies` rows for **every phase in the cascade**
  (`db/repositories.py:216-224`). The cascade from any rewind target (4, 4b, 5, 5b) includes
  `phase_5c_pre_writing_gate` itself (`phase_catalog.py:63-69`).
- On the next gate visit, `get_or_create_recovery_policy` recreates the row with
  `current_rewinds=0`. If the blocking condition is not fixed by the rewind (for example,
  deterministic PRISMA arithmetic mismatch, or a citation catalog mismatch that re-extraction does not
  change), the graph loops 4 -> 4b -> 5 -> 5b -> 5c -> 4 ... indefinitely, re-spending extraction
  LLM cost each time.
- Tests only cover single transitions with a pre-seeded exhausted policy
  (`tests/integration/test_graph_transitions.py:258-280`); no multi-iteration test exists.

### F2 (S1) Resume produces different manuscript facts than a straight-through run

`load_resume_state` restores only kappa. These fields are set in memory and read by writing,
synthesis, or finalize, but default to 0/empty/False on resume:

| Field | Set at | Consumed at |
|---|---|---|
| `batch_screen_forwarded/excluded/validation_n/validation_npv/borderline_forwarded`, `batch_screener_model`, `batch_screen_threshold` | `screening_runner.py:589-620,696` | `runners/writing/setup.py:310-315` (Methods grounding) |
| `fulltext_sought`, `fulltext_not_retrieved` | `screening_runner.py:755-819` | `setup.py:323-324` |
| `sparse_evidence_mode` | `screening_runner.py:1135` | `synthesis_runner.py:217-219` (**controls whether meta-analysis runs**), `setup.py:325` |
| `excluded_non_primary_count` | `extraction_runner.py:950` | `setup.py:347` |
| `heuristic_assessment_count` | `extraction_runner.py:1020` | `setup.py:305` |
| `search_queries`, `connector_init_failures` | `search_runner.py:204,311` | `finalize_runner.py:141,225-227` (PROSPERO form, run summary) |
| `rag_sections_*` | writing | `finalize_runner.py:231-236` |
| `kappa_n` | `screening_runner.py:930` | Restored from `summary.sample_size`/`kappa_n`, but the emitted payload only has `kappa` (`screening_runner.py:1199-1204`), so it is always 0 after resume |

Kappa restoration reads `event_log`, which the CLI path only writes after a clean exit
(`main.py:460-462`). A CLI run that crashes loses kappa on resume.

This violates the "one canonical source of truth for counts" contract in `llm-output.mdc`.
It is also the reason "resume from phase X" can pass all gates while producing a Methods section
that says zero records were batch-screened or that no full texts were sought.

### F3 (S1) Embedding failures persist zero vectors that are treated as success

- `embed_texts` catches any batch exception and returns `[[0.0] * dim]` for the batch
  (`src/rag/embedder.py:62-65`).
- `EmbeddingNode` persists them (`embedding_node.py:139-157`) and logs a zero-cost record.
- Resume skips any paper with at least one chunk row (`embedding_node.py:54-62`), so the corrupt
  vectors are permanent.
- The pre-writing gate checks only `DISTINCT paper_id` presence in `paper_chunks_meta`
  (`helpers/pre_writing_gate.py:80-89`), so it passes.
- `zip(all_chunks, embeddings)` (`embedding_node.py:148`) would also silently truncate on a length
  mismatch.

### F4 (S1) Cost budget is configured but never enforced

`gates.cost_budget_max: 30.0` (`config/settings.yaml`) feeds `GateRunner.run_cost_budget_gate`
(`gates.py:183-200`), which has **no call sites**. The same is true for `run_resume_integrity_gate`
(`gates.py:202-212`) and `run_citation_lineage_gate` (`gates.py:166-181`). Combined with F1, a run
has no cost ceiling.

### F5 (S2) Workflows die on every API restart; no worker isolation or lease

- Runs execute as tasks in the API event loop (`web/state.py:477`, `:608`).
- Project rules require `pm2 restart litreview-api` after every `src/` change
  (`pm2-restart.mdc`, `subagents.mdc`), which cancels every in-flight run.
- Startup marks every `running` row `interrupted` (`web/app.py:77-87`) with no auto-resume and a
  hard-coded `runs` root.
- The event buffer is flushed every 5s or on durable events (`web/event_store.py:118-145`), so
  eventual events in the last window are lost on crash.
- The CLI can resume the same workflow the API is running (no claim), with two writers on one
  runtime.db and two rate limiters on one key.

### F6 (S2) Shared-connection concurrency inside phases

See section 3.2. Extraction (`extraction_runner.py:149`, fan-out at `:465`, `:920`) and screening
(`screening_runner.py:98`, `DualReviewerScreener` concurrency 5) share one connection across
concurrent tasks. Every repository method calls `commit()` itself (for example
`repos/papers.py:171`, `repos/workflow_state.py:61,100,157`), so there are no atomic multi-row
units such as "extraction record + RoB + cohort row for paper P".

### F7 (S2) Silent data loss in repository and journal layers

- `PapersRepo.save_paper` catches `(sqlite3.IntegrityError, Exception)` and, if the NULL-DOI retry
  also fails, only logs (`repos/papers.py:116-134`). The paper is missing, and later FK inserts for
  it fail or get filtered (`repositories.py:110-128` "skipped N decisions for non-existent
  paper_ids").
- Step journal start/complete swallow all persistence errors (`helpers/step_journal.py:40-47,
  81-88`). Runners wrap journal starts in `except Exception: pass` (`search_runner.py:94-95`,
  `writing_runner.py:65-66`, `finalize_runner.py:53-54`).
- The CSV-masterlist branch of search returns without completing its step (`search_runner.py:197`),
  leaving a `running` row until the next attempt reconciles it to `skipped`.
- Embedding cost record failures are logged at DEBUG (`embedding_node.py:132-133`). Writing
  manifests and fallback events are wrapped in a single `except Exception` at DEBUG
  (`writing_runner.py:235-278`); `grounding_hash` is just the citation catalog hash (`:238-243`).
- `resolve_resume_next_phase` swallows registry errors (`start_runner.py:140-147`).
- `CitationRepository.ensure_schema` does DDL with `except Exception: pass`
  (`repositories.py:289-319`): a second, ad-hoc migration path outside `run_migrations`.
- `merge_papers_from_parent` swallows per-row errors and writes `dual_screening_results` with
  `workflow_id='merged'` and `stage='stage1'` (`repositories.py:620-626`), neither of which matches
  the real workflow id or the stage vocabulary (`title_abstract` / `fulltext`), so merged decisions
  are invisible to every query.
- Counts: about 90 `except Exception` in scope (extraction 15, post_assembly 12, finalize 10,
  registry 8), 21 of them bare `pass`.

### F8 (S2) Config and settings are not snapshotted for deterministic replay

- `load_resume_state` applies `apply_execution_profile` using the **workspace**
  `config/review.yaml` profile, then swaps in the snapshot review (`resume.py:125-134`), so
  settings are tuned by the wrong profile.
- `settings.yaml` (model IDs, thresholds, concurrency, gate profile) is never snapshotted. A resume
  after editing settings runs later phases with different models or thresholds than earlier phases.
- If the snapshot fails validation, resume falls back to the workspace review with only a warning
  (`resume.py:133-134`): the exact placeholder-leak scenario the comment says it prevents.
- `config_hash` for topic matching hashes the workspace file, not the snapshot
  (`workflow.py:372`, `:438`).
- Workflow-specific configs live in `config/` (`review_wf0114_revision.yaml`,
  `review_gamification.yaml`), contrary to `rerun-workflows.mdc`.
- `llm_available` returns True if **any** required key is present (`helpers/runtime.py:59-62`),
  so a missing provider key surfaces mid-phase rather than at start.

### F9 (S2) Split-brain status between registry and runtime.db

- Finalize writes the registry `completed` before writing the runtime `workflows.status` and the
  `finalize` checkpoint (`finalize_runner.py:263-272`). A crash in between leaves registry
  `completed` (so `run_workflow` will not offer resume, `workflow.py:440`) while the checkpoints
  say finalize is incomplete.
- Gate-failure paths update the runtime DB and then the registry, each with its own connection
  (`search_runner.py:160-161`, `screening_runner.py:1160-1161`, `extraction_runner.py:1053-1054`).
- Resume routing trusts the registry over checkpoints for HITL/PROSPERO
  (`start_runner.py:141-145`). A stale `awaiting_prospero` re-runs Search on a workflow that has
  already finished search.
- The web layer has a separate reconciler (`web/lifecycle_reconciler.py`, "startup repair") to
  patch up the inconsistency after the fact.

### F10 (S2) Migrations run on every connection and have fragile semantics

- `run_migrations` runs on every `get_db` (`database.py:750`).
- `_apply` splits SQL on `;` (`database.py:52`), which breaks any statement containing a literal
  semicolon, and ignores "duplicate column" / "already exists" errors, so partially applied
  migrations get stamped as applied.
- Atomicity of the table-rebuild migration 20 (`database.py:406-510`: CREATE v20, INSERT...SELECT,
  DROP, RENAME) relies on Python `sqlite3` implicit-transaction behavior rather than an explicit
  `BEGIN`/`COMMIT`.
- The schema is defined twice: desired state in `schema.sql` plus 23 ordered deltas in
  `database.py`, plus the ad-hoc DDL in `CitationRepository.ensure_schema`.
- The compatibility hack string-replaces an index DDL out of `schema.sql` (`database.py:35-40`).

### F11 (S3) God modules and pass-through layers

- Over 1000 lines in scope: `runners/screening_runner.py` (1243; `run_screening_node` alone runs
  about 1160 lines, `:83-1243`), `db/repos/writing.py` (1113), `runners/extraction_runner.py` (1099;
  one function, `:136-1099`). `context.py` is 968.
- `workflow.py:123-308` is about 185 lines of one-line wrappers kept "for backward compat/tests",
  re-exporting helper functions under `_`-prefixed names.
- `_rc`, `_journal_step_start`, and `_journal_step_complete` wrappers are copy-pasted in
  `search_runner.py:41-76`, `screening_runner.py:46-81`, and `extraction_runner.py:67-117`.
- `WorkflowRepository.__getattr__` delegates to nine sub-repos by first match
  (`repositories.py:73-83`), which defeats static typing and IDE navigation. The
  `domain_repositories.py` wrapper adds a third layer, used only by `web/routers/validation.py`.
- `screening_runner.py:1192` uses `locals().get("stage2", [])` to read a variable that may not be
  bound on some paths.
- Phase key strings are duplicated as literals across runners, `ResumeStartNode`, the frontend
  (`constants.ts`), and `rollback_phase_data` index comparisons (`repositories.py:206-278`).

### F12 (S3) Docs vs code drift

| Claim | Reality |
|---|---|
| "No untyped dicts across phase boundaries" (AGENTS/overview) | `ReviewState` dataclass with dict fields; setup returns a `dict`; `End[dict]` annotations; free-form events |
| "Every method in repositories.py accepts and returns Pydantic models" (`sqlite.mdc`) | Tuples/dicts returned (e.g. `get_all_citations_for_export`, `get_checkpoints -> dict[str,str]`) |
| Control plane = registry (`ARCHITECTURE.md` "Runtime planes") vs control plane = `workflow_steps`/`recovery_policies` (`overview.mdc`) | Both are used, with no ordering between them (F9) |
| "Rewind clears ... recovery policies through `rollback_phase_data`" (`ARCHITECTURE.md` Resume and rewind) | Documented and implemented, and it is exactly what breaks F1 |
| Recovery policies drive "attempt 2 of 3" and prevent unbounded retries (`models/workflow.py:249-253`) | Only one call site; retries never counted |
| "All I/O is async" | Sync `Path.write_text`, YAML reads, protocol generation, and `render_rob_traffic_light` run inside async phases |
| Resume prompt "phase N/7" (`workflow.py:447`) | `PHASE_ORDER` has 11 phases |
| `EmbeddingNode` docstring "Idempotent on resume" (`embedding_node.py:4`) | Only per paper, and it accepts corrupt vectors (F3) |
| Replay tests "re-execute pipeline helper code" | `test_workflow_replay_execution.py` asserts `count >= 0` |

---

## 5. Re-architecture recommendations (ranked by impact / effort)

Impact: H/M/L. Effort: S (under 1 day), M (1-3 days), L (a week or more).

### R1 (H/S) Stop the bleeding: fix the three S1 correctness bugs first

1. **F1:** exclude the gate's own policy from rollback. Simplest option: in `rollback_phase_data`,
   never delete `recovery_policies` for `phase_5c_pre_writing_gate` when invoked from the gate.
   Cleaner option: move policies to a table keyed by `(workflow_id, policy_key)` that rollback
   never touches, and reset it only on explicit user `from_phase` resume. Add a test that runs
   `RUN_GRAPH` from `PreWritingGateNode` with a permanently failing check and asserts termination
   after `max_rewinds + 1` gate visits.
2. **F3:** make `embed_texts` raise (or return a per-item `None`) on batch failure. Persist only
   real vectors, record a `fallback_events` row, and have the pre-writing gate check
   `COUNT(chunks with non-zero norm) == expected chunk count` per paper.
3. **F4:** call `run_cost_budget_gate` at every phase boundary (inside the harness from R3) and
   treat FAILED under the strict profile as `End(gate_blocked)`.

### R2 (H/M) Durable typed phase outputs; delete load-bearing in-memory state

Introduce one Pydantic model per phase, for example `SearchOutput`, `ScreeningOutput`
(all batch/fulltext/kappa counters, `sparse_evidence_mode`), `ExtractionOutput`
(`excluded_non_primary_count`, `heuristic_assessment_count`), `WritingOutput` (RAG counters).
Persist each as JSON in a new `phase_outputs(workflow_id, phase, generation, schema_version,
payload_json, input_digest, created_at)` table **in the same transaction as the checkpoint**.

- `load_resume_state` hydrates `ReviewState` exclusively from `phase_outputs` plus canonical
  tables, never from `event_log`.
- Writing grounding (`runners/writing/setup.py`) and finalize read from `ScreeningOutput` etc.,
  not from `state.*`.
- `ReviewState` shrinks to identity plus paths plus a cache of loaded outputs, and becomes a
  Pydantic model.
- Fixes F2 and most of F12's typing drift, and it is the foundation for replay (R6).

### R3 (H/M) One phase-runner harness that owns the lifecycle

Replace per-runner boilerplate with a single `run_phase(phase_key, fn)` used by every node:

```python
async def run_phase(state, phase: PhaseKey, body: Callable[[PhaseCtx], Awaitable[PhaseOutput]]):
    if await checkpoints.is_completed(phase, state.generation):
        return await outputs.load(phase)              # skip-if-done (no unconditional re-run)
    step = await journal.start(phase, input_digest=digest(state, phase))
    await gates.cost_budget(state)                    # F4
    try:
        out = await body(PhaseCtx(...))
    except TransientError as e:                       # classified, not swallowed
        await journal.fail(step, FailureCategory.TRANSIENT, RecoveryAction.RETRY); raise
    except GateFailure as e:
        await journal.fail(step, FailureCategory.TERMINAL, RecoveryAction.ABORT); return End(...)
    async with uow() as tx:                           # one transaction
        await outputs.save(tx, phase, out)
        await checkpoints.complete(tx, phase)
        await journal.succeed(tx, step, output_digest=digest(out))
    return out
```

- Nodes check their own checkpoint (removes the "downstream always re-runs" property and the stale
  `awaiting_prospero` re-search in F9).
- Journal writes are not optional: if the control-plane write fails, the phase fails.
- Retries use `recovery_policies` with `TRANSIENT/RETRY` at phase granularity, with backoff.
- Removes the `_rc`/`_journal_*` duplication (F11) and the `workflow.py` wrapper layer.

### R4 (H/M) Separate worker process with a DB lease

- Move `run_workflow` execution out of FastAPI into a `litreview-worker` PM2 process (or N
  workers). The API enqueues by writing a `run_requests` row and reads status from the DB.
- Lease: add `lease_owner`, `lease_expires_at` columns to the registry; the worker renews every
  heartbeat and takes over expired leases by calling resume (auto-recovery after restarts).
  The CLI must acquire the same lease (fixes concurrent CLI+API writers).
- Events: the worker writes `event_log` directly (synchronously for durable types); the API tails
  `event_log` for SSE. This removes the in-memory `_active_runs` replay buffer and the 5s loss
  window.
- A backend-only restart of the API then no longer kills runs; worker deploys can drain (finish
  current phase, release lease).
- Make the rate limiter cross-process (a SQLite token bucket table, or keep one worker per API
  key), and pass callbacks per call rather than at construction (F-3.3).

### R5 (M/S) Single status authority and ordered writes

- The runtime DB `workflows.status` plus checkpoints are authoritative; the registry is a
  derived index updated **after** the runtime commit, and rebuilt from runtime DBs on startup
  (the reconciler already has the logic).
- HITL/PROSPERO parking becomes a checkpoint status (`awaiting_review` on a `human_review`
  checkpoint key added to `PHASE_ORDER`) instead of a registry-only flag.
- `WorkflowRunResult.from_summary`: unknown status must raise, not default to `COMPLETED`.

### R6 (H/M) Golden replay and resume-equivalence tests

- **Resume equivalence:** for a small deterministic fixture (offline LLM stubs, fixed connector
  cassettes), run straight-through and also crash-and-resume at every phase boundary; assert
  identical `phase_outputs` payloads and identical manuscript grounding blocks. This would have
  caught F2 and F3.
- **Gate loop test:** permanently failing pre-writing check must terminate (F1).
- **Fault injection:** wrap `get_db` / repository commits with a test hook that raises on the Nth
  write; assert the run either completes or fails with a classified step, never with missing rows
  plus a `completed` checkpoint.
- **Replay fixtures:** upgrade `tests/fixtures/replay/runtime.db` tests from `count >= 0` to
  golden snapshots of PRISMA counts, cohort membership, and `phase_outputs`, regenerated via
  `scripts/repair.py regen-replay-fixture`.
- **Connector cassettes:** record/replay HTTP for search connectors so Search is reproducible in
  CI.

### R7 (M/M) Unit-of-work and connection discipline

- One connection per phase task, with explicit `async with uow.transaction():` for
  multi-row units (paper + decision + cohort row). Repositories stop calling `commit()`.
- Concurrent tasks either get their own connection (WAL handles many readers and serialized
  writers) or send writes through a single writer queue.
- `get_db` must not migrate. Migrate once per DB at process start / first open (cache the
  migrated path set), and require an explicit `db_path` (no default).

### R8 (M/S) Snapshot settings and make config immutable per run

- Write `settings_snapshot.yaml` next to `config_snapshot.yaml` at Start. Resume loads both
  snapshots, applies the execution profile from the snapshot review, and fails hard if a snapshot
  is invalid.
- `config_hash` = hash of the snapshot pair.
- `llm_available` must check that all required keys are present; fail at Start.
- Move workflow-specific YAMLs out of `config/`.

### R9 (M/M) Migration hardening

- Freeze `schema.sql` as "baseline v0" and move every change into numbered migration files run
  inside explicit `BEGIN IMMEDIATE ... COMMIT`, stamped only on success; delete the `;` splitter
  and the error-string tolerance.
- Fold `CitationRepository.ensure_schema` into a numbered migration.
- Add a CI test that migrates a v0 DB and the replay fixture DBs and compares
  `sqlite_master` with a fresh-schema DB.

### R10 (M/L) Break up god modules along the harness seams

- `screening_runner.py` -> `prefilter.py` (keyword/BM25/cap), `batch_rank.py`,
  `dual_review.py`, `fulltext.py`, `citation_chasing.py`, each returning a typed sub-output that
  composes into `ScreeningOutput`.
- `extraction_runner.py` -> `extract_one.py`, `assess_quality.py`, `grade_aggregate.py`,
  `primary_filter.py`.
- Replace `WorkflowRepository.__getattr__` with explicit sub-repo access
  (`repo.papers.save_paper`) and delete `domain_repositories.py`.
- Replace the `ResumeStartNode` `if` ladder with a `PHASE_NODES: dict[PhaseKey, type[BaseNode]]`
  from `phase_catalog`, with `PhaseKey` a `str` enum shared with the frontend via generated types.

### R11 (L/S) Exception policy lint

- Add a ruff rule set (`BLE001`, `S110`, `SIM105`) with an allowlist. Any remaining broad catch
  must record a `fallback_events` row (module, reason, paper_id) so degraded mode is visible in
  diagnostics and to the manuscript readiness scorecard.

### Suggested sequencing

| Order | Item | Why first |
|---|---|---|
| 1 | R1 (F1, F3, F4) | Unbounded cost and silent corruption today; small patches |
| 2 | R6 gate-loop + resume-equivalence tests (skeleton) | Locks in R1, measures R2 |
| 3 | R8 settings snapshot | Cheap determinism win |
| 4 | R2 phase outputs | Fixes resume facts; enables golden replay |
| 5 | R3 harness | Depends on R2 output models |
| 6 | R5 status authority | Simplifies R4 |
| 7 | R4 worker + lease | Largest operational robustness win |
| 8 | R7, R9, R10, R11 | Structural hardening |

---

## Appendix A - Key file index

| Concern | File |
|---|---|
| Graph + entrypoints | `src/orchestration/workflow.py` |
| Phase keys | `src/orchestration/phase_catalog.py` |
| State | `src/orchestration/state.py` |
| Resume | `src/orchestration/resume.py`, `src/orchestration/runners/start_runner.py` |
| Gates | `src/orchestration/gates.py`, `src/orchestration/helpers/pre_writing_gate.py`, `src/orchestration/runners/pre_writing_gate_runner.py` |
| Step journal | `src/orchestration/helpers/step_journal.py`, `src/db/repos/workflow_state.py` |
| Rollback | `src/db/repositories.py:193-281` |
| Migrations | `src/db/database.py:26-542`, `src/db/schema.sql` |
| Registry | `src/db/workflow_registry.py` |
| Web run execution | `src/web/state.py:430-680`, `src/web/event_store.py`, `src/web/app.py:73-120` |
| Rate limiting | `src/llm/rate_limiter.py`, `src/llm/shared_rate_limiter.py` |
