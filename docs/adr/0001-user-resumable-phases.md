# ADR-0001: User-resumable phases exclude phase_7_audit

## Status

Accepted

## Context

`PHASE_ORDER` in `src/orchestration/resume.py` includes `phase_7_audit` as an internal orchestration checkpoint. The web API, frontend resume UI, and pipeline docs expose a user-resumable subset.

## Decision

- Export `USER_RESUMABLE_PHASE_ORDER` from `src/orchestration/resume.py` (all phases except `phase_7_audit`).
- Web layer imports this list instead of maintaining a duplicate `_RESUME_PHASE_ORDER`.
- Frontend `RESUME_PHASE_ORDER` must match `USER_RESUMABLE_PHASE_ORDER`.

## Consequences

- Users cannot resume directly into audit; audit runs as part of the writing/finalize path.
- Single source prevents API validation drift.
