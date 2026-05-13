# Implementation Status and Parity Checklist

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
