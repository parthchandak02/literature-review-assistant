# Doc Routing (this repository)

This project does **not** use root `CONTEXT.md` / `CONTEXT-MAP.md` as the
grilling glossary. Canonical agent docs live under `.cursor/docs/`.

## Entry points

1. `AGENTS.md` - onboarding and source-of-truth priority
2. `.cursor/docs/INDEX.md` - lifecycle routing narrative
3. One task contract from `.cursor/docs/` (see map below)
4. Code in `src/` and `frontend/src/` when docs and claims diverge

## Doc map for grilling

| Topic | Canonical doc | What to pressure-test |
|-------|---------------|------------------------|
| Runtime planes, invariants, SoT paths | `ARCHITECTURE.md` | Control vs data plane, typed boundaries, model-id config |
| Phase lifecycle, checkpoints | `PIPELINE.md` | Build-phase labels vs runtime checkpoint keys |
| Validation / parity readiness | `IMPLEMENTATION_STATUS.md` | Acceptance surfaces before claiming done |
| API / SSE ownership | `API_CONTRACT.md` | Endpoint ownership, resume surfaces, parity |
| DB / registry truth | `PERSISTENCE.md` | `runtime.db` vs `workflows_registry.db`, table ownership |
| Frontend structure | `UI_ARCHITECTURE.md` | View model, `frontend/src/lib/api.ts` contract |
| LLM routing and cost | `LLM_AND_COSTS.md` | Cost accounting, fallback, rate limits |
| Endpoint parity anchor only | `API_ENDPOINTS.md` Section 10.1 | Compatibility checks, not architecture guidance |

## Domain vocabulary cues (from this repo)

Prefer these existing terms when sharpening language:

- **Build phases (1-8)** vs **runtime checkpoints** (`PHASE_ORDER` in `src/orchestration/resume.py`) - not interchangeable
- **Included primary cohort** via `study_cohort_membership` (`synthesis_eligibility='included_primary'`)
- **Cost truth** via `cost_records`
- **Typed phase boundaries** via Pydantic models in `src/models/`
- **Control-plane records**: `WorkflowStepRecord`, `RecoveryPolicyRecord`, `WritingManifestRecord`

## ADR location

Architecture Decision Records live in `docs/adr/` (sequential `000N-slug.md`).
See [ADR-FORMAT.md](./ADR-FORMAT.md). Do not require or create `CONTEXT.md`.
