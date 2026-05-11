# UI Architecture Contract

## Frontend Source of Truth

- App shell and routing: `frontend/src/App.tsx`
- API client: `frontend/src/lib/api.ts`
- Phase constants: `frontend/src/lib/constants.ts`
- SSE hook: `frontend/src/hooks/useSSEStream.ts`

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
