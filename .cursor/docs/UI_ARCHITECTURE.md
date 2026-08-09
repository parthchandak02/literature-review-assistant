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

Primary run tabs (`RunTab` in `frontend/src/context/runSessionTypes.ts`; rendered in `frontend/src/views/RunView.tsx`):

- Config (`config`)
- Activity (`activity`)
- Data (`database`)
- Cost (`cost`)
- Results (`results`)

`Review Screening` (`review-screening`) is conditional and appears when workflow status is `awaiting_review`.

## Results Tab Categories

The Results tab (`results`) uses a second navigation layer inside `ResultsView` (`frontend/src/views/ResultsView.tsx`). Category ids and resolution logic live in `frontend/src/lib/resultsCategories.ts` (vitest-covered).

| Category id | When shown | Primary content |
|-------------|------------|-----------------|
| `manuscript` | `doc_manuscript` artifact exists | `ManuscriptViewer`, export actions in `ManuscriptActions` |
| `figures` | PRISMA diagram path or custom diagram pipeline | `PrismaDiagramCard`, `CustomDiagramsCard`, figure rows from `ArtifactFileList` |
| `quality` | Run has `exportRunId` (completed export path) | `GradeSofCard`, `EvidenceNetworkSection` |
| `files` | Always (with results) | `ProsperoDownloadsCard`, document groups in `ArtifactFileList` |
| `references` | Always (with results) | `ReferencesView` (`embedded`) |

**Defaults:** Manuscript when present; otherwise Files.

**Deep links:** `submissionFocusTarget === "reference-papers"` opens Files and highlights the Reference papers ZIP row (`SUBMISSION_FOCUS_RESULTS_CATEGORY` in `resultsCategories.ts`).

**Legacy URLs:** `/run/:id/quality` and `/run/:id/references` still parse to the Results tab (`parseRunUrl`); category is not encoded in the URL yet.

## Draft Run Shell

`/run/draft/config` uses the run shell with `ConfigView` in draft mode before a real workflow exists. Not a separate route contract.

## Run Chrome

- **App bar:** topic breadcrumb (copy on click); "New Review" on setup
- **Run info strip:** single line in `RunView` — status, workflow id, date, paper funnel, cost link, live indicator when streaming
- **Tabs:** `GlassTabs` row below the info strip
- **Phase progress:** Activity tab only (`PHASE TIMELINE` + log). No duplicate phase chips in the header.

## API Usage Boundaries

- Prefer typed helpers in `frontend/src/lib/api.ts`.
- SSE run stream is consumed via `useSSEStream` against `/api/stream/{run_id}`.
- Health polling uses `/api/health`.

## Frontend/Backend Phase Alignment

- Frontend `RESUME_PHASE_ORDER` must match backend `USER_RESUMABLE_PHASE_ORDER` in `src/orchestration/resume.py` (excludes internal `phase_7_audit`).
- Frontend display `PHASE_ORDER` can include UI-only subphase labels for richer progress rendering.

## Production Serving Contract

- Production URL is served by FastAPI from built `frontend/dist/`.
- Vite dev server auto-reload does not imply production asset refresh.
