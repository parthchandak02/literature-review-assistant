# Re-architecture plan (2026-09-26)

Goal: a lit-review pipeline that is robust and battle-tested end to end, with no loss in
output quality, and that offloads typed decision work to Jev (TypeSafe) where it improves
speed, scale, or reviewer independence.

## Reports (evidence, file:line)

| File | Scope |
|---|---|
| `00-jev-reference.md` | Verified Jev API, limits, and rollout rules |
| `01-orchestration-persistence.md` | Phase graph, resume, recovery, DB, concurrency |
| `02-llm-callsites-jev.md` | LLM layer + all 30 call sites, real cost, Jev fit |
| `03-pipeline-modules-quality.md` | Screening -> export modules, contracts, methodology |
| `04-web-frontend.md` | 69 endpoints, UI views, drift |
| `05-tests-scripts-health.md` | Test inventory, gates, baseline results |

## What the map says (headline)

1. **The pipeline reports success when it should not.** wf-0001 finished `done` while its own
   audit returned `major_revisions` (8 blocking findings) because `audit_gate_mode: advisory`.
   The abstract was an empty-section placeholder whose manifest said `passed, fallback_used=0`.
2. **Facts reach the manuscript through four unreconciled paths** (patch sentences, LLM
   prose, evidence-assembler templates, export tables), so the manuscript contradicts
   itself (Table 1 has 4 of 6 studies; kappa n 194 vs 209; 1 exclusion vs 4 reasons).
3. **Correctness bugs (verified in code):**
   - Pre-writing gate rewind bound is erased by its own rollback cascade
     (`rollback_phase_data` deletes `recovery_policies` for `phase_5c`), so it can loop forever.
   - Failed embeddings are stored as zero vectors (`src/rag/embedder.py:62-65`) and pass gates.
   - PRISMA full-text exclusion reasons count reviewer votes, not final decisions
     (`src/db/repos/screening.py:136-171`).
   - Cost budget, resume-integrity, and citation-lineage gates are never called.
   - Retry classifier matches `"rate"` inside words like "moderate".
   - Missing RoB 2 domains silently default to "low".
4. **Resume is not equivalent to a straight run:** ~15 `ReviewState` fields live only in
   memory (counts that feed Methods/PRISMA/meta-analysis gating); `settings.yaml` is not
   snapshotted; the API process hosts workflows, so every `pm2 restart` kills runs.
5. **Methodology gaps:** GRADE graded per study, not per outcome; CASP/MMAT never feed RoB
   downgrade; 3 GRADE domains hardcoded 0; keyword-prefilter removals not reported in the
   PRISMA "removed by automation" box; narrative vote-count mixes benefit and harm.
6. **Anti-patterns the repo's own rules forbid:** `grounding_patches.py` (keyword check +
   canned sentences), humanizer word blocklists and a deleting regex.
7. **Tests:** `make check-local` green (1,177 unit + smoke + 172 frontend + replay), but the
   full suite has 13-18 red integration tests; there is no full-graph E2E with fake
   LLM/search; running tests mutates a committed fixture (`tests/fixtures/replay/runtime.db`).
8. **Jev economics:** of wf-0001's $1.21, only ~$0.09 is Jev-addressable (writing, humanizer,
   and diagram images dominate). Jev's value here is **quality and scale**: an independent
   second screener (reviewers A/B are the same model and temperature), removal of the
   200-paper screening cap, sub-second reranking (34 s/section today), and typed judgments
   (RoB signalling questions, GRADE domains, effect direction, citation-support checks) that
   are currently hardcoded, heuristic, or skipped.

## Decisions (user, 2026-09-26)

- Failed contracts/audit: finish all artifacts, run status `needs_revision` (not `done`).
- Jev: `on` everywhere it fits, with confidence routing (LLM only on low confidence /
  disagreement). Decisions still logged to `jev_decisions` for calibration reporting.
  Thresholds for anything that excludes a paper stay conservative.
- Screening cap: raise/remove once Jev screening is live.
- Humanizer + custom diagrams: keep both; rebuild humanizer as a structured rewrite with
  contract checks (no blocklists / deleting regex).
- Worker split: research alternatives first (open).
- Live rerun budget: up to ~$25 total, reported as spent.
- Landing: commit directly to `main` per phase.

## Target architecture

```
Control plane (FastAPI)  --enqueue-->  runs queue (SQLite)  <--lease--  Worker process
      |  read-only views                                            |
      v                                                             v
  run DB (single source of status)  <--typed phase outputs--  PhaseRunner
                                                                    |
            +------------------+------------------+----------------+
            v                  v                  v                v
      Deterministic core   Decision layer     Generation layer   Contracts/gates
      (stats, PRISMA,      (Jev first,        (main LLM:         (blocking, typed,
       GRADE algorithms,    LLM escalation,    prose, extraction, read ReviewFacts)
       ReviewFacts IR)      shadow logging)    diagrams)
```

- **PhaseRunner**: one shared wrapper that journals, checks the budget, skips when the typed
  output for (phase, input hash) already exists, and writes the output and checkpoint in
  one transaction. Resume reads only persisted outputs.
- **ReviewFacts**: one deterministic, typed facts object built from the DB (PRISMA counts,
  cohort, kappa, GRADE rows, table rows). Every number in the manuscript, protocol, and exports
  is rendered from it; LLM prose may cite facts only through placeholders validated at
  generation time.
- **Decision layer**: `JevClient` + `DecisionRouter` with per-surface `off|shadow|on`
  in `config/settings.yaml`, `jev_decisions` table, cost logging, fail-open to the LLM path.
- **Gates block**: a run whose contracts or audit fail ends as `needs_revision`, not `done`
  (artifacts still produced and inspectable).

## Status (2026-09-26)

| Phase | Status |
|---|---|
| P0 | Done (`b208751`) |
| P1 | Partial: `needs_revision` status + `audit_gate_mode: needs_revision` shipped; `cost_records.workflow_id` passed at LLM call sites (`2655940`) |
| P2 | Partial: `ReviewFacts` in `src/manuscript/review_facts.py` feeds pre-writing gate, writing setup, audit, contracts, readiness, PRISMA flow export; `grounding_patches.py` and humanizer regex/blocklists not yet removed |
| P3 | Not started |
| P4 | Stage 0 done: `ops_pm2.sh restart` refuses while runs are live (`--force` overrides); uvicorn `--timeout-graceful-shutdown 30`, PM2 `kill_timeout` 70000 in `ecosystem.config.example.js`. Stages 1-2 not started |
| P5 | Partial: four surfaces (`screening_reviewer_b`, `batch_pre_rank`, `study_design`, `rag_rerank`) with `off\|shadow\|live` (repo: `screening_reviewer_b: off`, other three `shadow`), `jev_decisions`, Jev cost pricing; eval shipped as `scripts/check.py jev-eval` (not `jev-calibration`). Not started: CASP/MMAT, RoB signalling, GRADE domains, effect direction, citation-support surfaces. No surface flipped to `live`. Live eval 2026-09-26 (wf-0001, 100 papers): Jev include recall 0.40 vs LLM reviewer B 0.69 vs final T/A (kappa 0.46 vs 0.70); only `exclude_confidence >= 0.99` had zero false excludes (54% coverage), so reviewer B stays LLM |
| P6-P7 | Not started |
| P8 | Partial: shared rate limiter keyed on actual provider key env vars |

Mode naming in code is `off|shadow|live` (this plan's `on` = `live`).

## Phased plan

Each phase ends with its own tests plus `make check-local`, `pm2 restart litreview-api`, and a commit.

**P0 — Stop the bleeding (small, verified bugs)**
Gate rewind bound survives rollback; zero-vector embeddings become recorded failures that
block the gate; PRISMA reason query uses the final decision; wire the budget gate; exact
transient-error classification with an overall retry cap; missing RoB domains -> recorded
failure, not "low"; honest writing manifests (placeholder => `fallback_used`); tests stop
mutating committed fixtures; fix the red integration tests.

**P1 — Truthful status and visible fallbacks**
Every fallback path records `fallback_events`; blocking gate mode; run status
`needs_revision`; `cost_records.workflow_id` always set; all LLM calls go through
`complete_validated` (or a logged raw path) with cost logging.

**P2 — ReviewFacts IR, single source of numbers**
Build `ReviewFacts` in `src/models/`; render PRISMA, tables, abstract numbers, and Methods counts
from it; cross-artifact consistency contract; delete `grounding_patches.py` and the
humanizer's deleting regex/blocklists, replacing them with generation-time structure.

**P3 — Durable PhaseRunner and faithful resume**
Persist the in-memory `ReviewState` fields; snapshot `settings.yaml` per run; the run DB is
the only status source; typed per-phase outputs + input hashes; per-task DB connections
and transactions; migrations once per process.

**P4 — Runs survive API restarts (per-run process + lease; see `06-run-survival-options.md`)**
A long-lived PM2 worker would still have to restart to load new orchestration code and would
kill its runs, so each run gets its own detached OS process instead.
- Stage 0: `ops_pm2.sh` warns/refuses when runs are live; uvicorn
  `--timeout-graceful-shutdown 10`.
- Stage 1 (independent of P3): API spawns one detached process per run
  (`start_new_session=True`, PM2 `treekill: false`); lease + heartbeat in the registry, taken
  by CLI and API alike (mutual exclusion); runner writes events to SQLite and SSE tails the DB
  with a persisted `run_id`; each run keeps the code it started with.
- Stage 2 (after P3): auto-resume only after crash/reboot/OOM, with a retry cap, and only
  when API keys resolve without the UI.

**P5 — Jev decision layer (shadow first)**
`src/llm/jev_client.py` (async aiohttp, pinned model from settings, cost records,
fail-open); `jev_decisions` table; surfaces in shadow: title/abstract screening as an
independent reviewer, CASP/MMAT items, RoB 2 / ROBINS-I signalling questions feeding
deterministic algorithms, GRADE domains, effect direction per outcome, study-design
classification, RAG rerank, citation-supports-claim checks. Calibration report command
(`scripts/check.py jev-calibration`) with agreement, recall on included studies, and
confidence bins. Flip surfaces to `on` only with approval.

**P6 — Methodology corrections**
GRADE per outcome; checklist routing by design (no qualitative CASP on quantitative
studies); CASP/MMAT feed the RoB domain; PRISMA automation box; narrative synthesis
by outcome domain and direction.

**P7 — Battle testing**
Full-graph E2E with a deterministic fake LLM/search/Jev provider; resume-at-every-boundary
equivalence test; fault injection (malformed LLM output, 429 storms, crash mid-phase,
Jev down); gate-loop termination test; add all of it to `make check-release`; live rerun
of wf-0001 from its `config_snapshot.yaml` and a fresh larger review.

**P8 — LLM layer hygiene and cost**
Disable thinking on non-reasoning utility calls (reranker spends ~3.5K tokens for 20
integers); rate limiter keyed on the real provider; no hardcoded temperatures; run-snapshot
settings everywhere.
