# UI Architecture Contract

## Frontend Source of Truth

- App shell and routing: `frontend/src/App.tsx`
- Run session provider and hook: `frontend/src/context/RunSessionProvider.tsx`, `frontend/src/hooks/useRunSession.ts`
- Run session composition: `frontend/src/hooks/useRunSessionState.ts`, `useLiveRunStream.ts`, `useRunSessionSync.ts`, `useRunSessionActions.ts`
- Run session types: `frontend/src/context/runSessionTypes.ts`
- Run URL parsing: `frontend/src/lib/runSessionUrl.ts`
- API client: `frontend/src/lib/api/` (barrel: `frontend/src/lib/api.ts`)
- Phase constants: `frontend/src/lib/constants.ts`
- SSE hook: `frontend/src/hooks/useSSEStream.ts`
- Sidebar: `frontend/src/components/Sidebar.tsx`, row model `frontend/src/components/sidebar/historyRowModel.ts`
- Sidebar note autosave hook: `frontend/src/hooks/useNoteAutosave.ts`

## Run Experience Model

Primary run tabs:

- Config
- Activity
- Data
- Cost
- Results
- References
- Quality

`Review Screening` is conditional and appears when workflow status is `awaiting_review`.

## API Usage Boundaries

- Prefer typed helpers in `frontend/src/lib/api.ts`.
- SSE run stream is consumed via `useSSEStream` against `/api/stream/{run_id}`.
- Health polling uses `/api/health`.

## Frontend/Backend Phase Alignment

- Frontend `RESUME_PHASE_ORDER` must match backend `PHASE_ORDER` in `src/orchestration/resume.py`.
- Frontend display `PHASE_ORDER` can include UI-only subphase labels for richer progress rendering.

## Production Serving Contract

- Production URL is served by FastAPI from built `frontend/dist/`.
- Vite dev server auto-reload does not imply production asset refresh.
