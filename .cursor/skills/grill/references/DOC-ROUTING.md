# Doc Routing (this repository)

This project does **not** use a root-level `CONTEXT.md`. Canonical agent docs live under `docs/` (`docs/CONTEXT.md` is the routing hub).

## Entry points

1. `AGENTS.md` - onboarding and source-of-truth priority
2. `docs/CONTEXT.md` - lifecycle routing narrative
3. One task contract from `docs/` (see map below)
4. Code in `src/` and `frontend/src/` when docs and claims diverge

## Doc map for grilling

| Topic | Canonical doc | What to pressure-test |
|-------|---------------|------------------------|
| Runtime planes, invariants, SoT paths | `docs/ARCHITECTURE.md` | Control vs data plane, typed boundaries, model-id config |
| Phase lifecycle, checkpoints | `docs/ARCHITECTURE.md#pipeline` | Build-phase labels vs runtime checkpoint keys |
| Validation / parity readiness | `docs/TASKS.md` | Acceptance surfaces before claiming done |
| API / SSE ownership | `docs/API.md` | Endpoint ownership, resume surfaces, parity |
| DB / registry truth | `docs/ARCHITECTURE.md#persistence` | `runtime.db` vs `workflows_registry.db`, table ownership |
| Frontend structure | `docs/UI.md` | View model, `frontend/src/lib/api.ts` contract |
| LLM routing and cost | `docs/ARCHITECTURE.md#llm-and-costs` | Cost accounting, fallback, rate limits |
| Endpoint parity anchor only | `docs/API.md#rest-endpoints` Section 10.1 | Compatibility checks, not architecture guidance |

## Domain vocabulary cues (from this repo)

Prefer these existing terms when sharpening language:

- **Build phases (1-8)** vs **runtime checkpoints** (`PHASE_ORDER` in `src/orchestration/resume.py`) - not interchangeable
- **Included primary cohort** via `study_cohort_membership` (`synthesis_eligibility='included_primary'`)
- **Cost truth** via `cost_records`
- **Typed phase boundaries** via Pydantic models in `src/models/`
- **Control-plane records**: `WorkflowStepRecord`, `RecoveryPolicyRecord`, `WritingManifestRecord`

## ADR location

Architecture Decision Records live in `docs/adr/` (sequential `000N-slug.md`).
See [ADR-FORMAT.md](./ADR-FORMAT.md). Use `docs/CONTEXT.md` as the routing hub; do not add parallel doc indexes elsewhere.
