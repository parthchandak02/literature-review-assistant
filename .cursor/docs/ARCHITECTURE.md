# Architecture Contract

## Purpose

The system automates systematic reviews from research question to submission artifacts while preserving deterministic evidence, reproducible persistence, and auditable LLM usage.

## Runtime Planes

- API and orchestration: `src/web/app.py`, `src/orchestration/workflow.py`, `src/orchestration/resume.py`
- Data plane: per-run `runtime.db` (`src/db/schema.sql`)
- Control plane: global `runs/workflows_registry.db` (resolved by `src/db/workflow_registry.py`)
- Frontend plane: `frontend/src/` with typed API contract in `frontend/src/lib/api.ts`
- Artifact plane: run directory outputs under `runs/YYYY-MM-DD/...`

## Always-On Invariants

- Fix process behavior in `src/` and `frontend/src/`, never by editing `runs/` artifacts.
- No untyped dict boundaries across phases; use models in `src/models/`.
- No LLM-computed statistics when deterministic computation exists.
- LLM calls must be tracked in `cost_records` with model and token accounting.
- Model IDs are configured in `config/settings.yaml`, not hardcoded in source.

## Canonical Source-of-Truth Paths

- Runtime graph: `src/orchestration/workflow.py` (`RUN_GRAPH`)
- Resume order: `src/orchestration/resume.py` (`PHASE_ORDER`)
- Typed contracts: `src/models/`
- DB schema: `src/db/schema.sql`
- Registry and workflow history: `src/db/workflow_registry.py`
- Stats precedence and truth rules: `src/db/source_of_truth.py`
- API surface: `src/web/app.py`
- Frontend API client: `frontend/src/lib/api.ts`
- Frontend phase constants: `frontend/src/lib/constants.ts`

## Phase Naming Rule

Build phases (1-8) are planning labels.
Runtime checkpoints are the backend keys in `src/orchestration/resume.py`.
Do not treat these naming systems as interchangeable.
