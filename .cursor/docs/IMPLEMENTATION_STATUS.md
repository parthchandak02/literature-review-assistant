# Implementation Status and Parity Checklist

## Before you commit (high-level changes)

If your work changes **architecture, phases/checkpoints, public API behavior, persistence/schema, or agent docs under `.cursor/`**, run through **Docs-to-Code Parity Checklist** below and the **Verification Gates** at the bottom of this file before committing. Then follow `.cursor/commands/3-pre-commit-workflow.md` for the actual commit/push sequence (see `general-rules` skill for full hygiene).

Narrow bugfixes that do not alter those contracts can rely on normal tests and hooks only.

## Runtime Completion Snapshot

Top-level runtime checkpoints listed in `src/orchestration/resume.py` are implemented and wired in `src/orchestration/workflow.py`.

## Known Critical Validation Surfaces

- Endpoint parity: `scripts/check_spec_endpoint_parity.py`
- Workflow replay validation: `scripts/validate_workflow_replay.py`
- Core backend tests: `tests/unit`, `tests/integration`
- Frontend contract checks: `frontend` lint and typecheck scripts

## Docs-to-Code Parity Checklist

Use this checklist before and after major refactors:

1. Every doc path reference resolves to an existing file.
2. Endpoint docs match `src/web/app.py` decorators.
3. Phase order docs match `src/orchestration/resume.py`.
4. Frontend phase constants and backend resume order stay aligned.
5. Table and schema claims map to `src/db/schema.sql` and repository code.
6. Rules, commands, and skills in `.cursor/` do not contradict each other.

## Drift Policy

When behavior changes:

- Update `.cursor/docs/*` first (canonical)
- Then update `.cursor/rules/*`, `.cursor/commands/*`, `.cursor/skills/*`
- Finally refresh root entry docs (`AGENTS.md`, `README.md`) and canonical `.cursor/docs/*` files

## Reliability Refactor Sequence

Use this sequence when planning major reliability refactors:

1. Contract convergence
   - Align runtime checkpoints to `src/orchestration/resume.py` and frontend `RESUME_PHASE_ORDER`.
   - Remove stale phase assumptions (for example, `phase_7_audit`) from docs/rules/comments.
2. Orchestration hardening
   - Ensure `RUN_GRAPH` transitions and resume routing are type-safe and deterministic.
   - Preserve compatibility for legacy checkpoint rows without reintroducing old checkpoint contracts.
3. Persistence and rewind guarantees
   - Keep rewind cleanup centralized in `WorkflowRepository.rollback_phase_data`.
   - Verify each rewound phase clears downstream artifacts, step journals, and recovery policies.
4. API/UI parity hardening
   - Keep endpoint docs aligned with `src/web/app.py`.
   - Keep frontend runtime progress flow (`PHASE_ORDER`) distinct from resume contract (`RESUME_PHASE_ORDER`).
5. Replay and regression gates
   - Re-run workflow replay and endpoint parity checks before shipping refactors.

## Verification Gates For Refactor Work

- Endpoint parity: `uv run python scripts/check_spec_endpoint_parity.py`
- Replay safety: `uv run python scripts/validate_workflow_replay.py`
- Backend regression sweep: `uv run pytest tests/unit -q` and targeted integration tests
- Frontend contract sweep: `cd frontend && pnpm lint && pnpm typecheck`
