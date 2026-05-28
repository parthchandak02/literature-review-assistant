# Context Glossary

- **Humanization**: Phase 6 post-write refinement that improves readability while preserving facts, citations, and numeric/statistical content.
- **HumanizerFlag**: A deterministic quality finding emitted by `src/writing/humanizer_checks.py`, classified as `high`, `medium`, or `low`.
- **Academic Manuscript Section**: Humanizer content type used for systematic review sections, with formal register and manuscript-safe constraints.

## Architecture (2026 deep-dive)

- **FullTextResolver**: Bounded context in `src/fulltext/` that resolves landing pages, tier-races PDF retrieval, and full-text reason codes. Vision table extraction remains in `src/extraction/table_extraction.py`.
- **RunStatsResolver**: Canonical async stats resolver in `src/db/stats.py`; history API and exports must not duplicate fallback SQL for included-paper counts or total cost.
- **RunRegistry / EventStore / LifecycleReconciler**: Split lifecycle modules under `src/web/` replacing the monolithic `state.py` responsibilities for in-memory runs, event persistence, and terminal-status reconciliation.
- **RunSession**: Frontend run-selection contract (`SelectedRun`, tab state, start/resume actions). Provider: `frontend/src/context/RunSessionProvider.tsx`; hook: `frontend/src/hooks/useRunSession.ts`; composed state in `useRunSessionState.ts` with live stream (`useLiveRunStream`), URL/sync effects (`useRunSessionSync`), and actions (`useRunSessionActions`). Helpers: `frontend/src/lib/runSession.ts`; URL parsing: `frontend/src/lib/runSessionUrl.ts`.
- **User-resumable phase**: Phases exposed in UI resume controls (`USER_RESUMABLE_PHASE_ORDER` in `src/orchestration/resume.py`). Internal-only phases such as `phase_7_audit` are excluded — see ADR-0001.
- **ControlPlaneService** (planned): Future encapsulation of `workflow_steps`, `recovery_policies`, and `writing_manifests` for diagnostics and replay tests.
