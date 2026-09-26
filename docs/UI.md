# UI

Frontend contracts and design rules for the research-ops dashboard (`frontend/src/`).

**Skill:** `.cursor/skills/frontend/SKILL.md` for token discipline and workflow.

## Source of truth

| Area | Path |
|------|------|
| App shell | `frontend/src/App.tsx` |
| Run session | `context/RunSessionProvider.tsx`, `hooks/useRunSession*.ts`, `lib/runSession.ts` |
| Types | `context/runSessionTypes.ts` |
| API client | `frontend/src/lib/api/` (barrel: `api.ts`) |
| Phases/status | `lib/constants.ts`, `lib/phaseProgress.ts` |
| SSE | `hooks/useSSEStream.ts` |
| Sidebar | `components/Sidebar.tsx`, `sidebar/historyRowModel.ts`, `hooks/useSidebarRuns.ts` (`partitionHistory`) |

## Run tabs (`RunTab`)

Rendered in `RunView.tsx` (`TAB_ITEMS`) in this order: `activity` (Activity), `results` (Results), `database` (Data), `config` (Config), `cost` (Cost). Ids and URLs are unchanged from the earlier order.  
`review-screening` appears when status is `awaiting_review`.

`GlassTabs` is an ARIA tablist: roving focus with Arrow Left/Right, Home, End; each tab `aria-controls` the `tabpanel-{id}` region in `RunView.tsx`.

## Results categories

Logic in `lib/resultsCategories.ts` (vitest-covered):

| Id | When shown |
|----|------------|
| `manuscript` | `doc_manuscript` exists |
| `figures` | PRISMA/custom diagrams |
| `quality` | Run has export id |
| `files` | Always |
| `references` | Always |

Default: Manuscript if present, else Files.

## Run chrome

- Topic breadcrumb in App bar
- Single-line info strip (status, workflow id, funnel, cost link)
- `GlassTabs` below strip
- Phase timeline on Activity tab only (no duplicate header chips)
- Run status announced via `aria-live="polite"` in `RunChrome.tsx`
- Finished runs show "Download submission package" (`SubmissionPackageButton`) in the chrome; Results Manuscript actions have an explicit "Package manuscript" (or "Rebuild package") step
- `needs_revision` status (contracts/audit failed, artifacts produced) has its own label/badge and a Results banner (`isNeedsRevisionStatus` in `lib/constants.ts`)

## Sidebar

- Settings button lives in the sidebar header (`SidebarHeader.tsx`)
- "Needs your input": `config_generating`, `config_ready`, `awaiting_prospero`, `awaiting_review`; "Reviews": other visible runs
- Stop run asks for confirmation (`ConfirmDialog` in `RunNavCard.tsx`)

## Setup and state

- API keys panel never receives server secrets; server-set keys show "Configured on server" (from `/api/config/env-keys/status`)
- Screening overrides persist per workflow in `sessionStorage` (`hooks/useScreeningReview.ts`)
- Offline banner ("Can't reach the server", Retry now) in `App.tsx`; suppressed while streaming

## Phase alignment

- `RESUME_PHASE_ORDER` must match backend `USER_RESUMABLE_PHASE_ORDER`
- Display `PHASE_ORDER` may include UI-only `fulltext_pdf_retrieval`
- Use `connectLiveRun` / `clearLiveRunUi` from `runSession.ts` for live-run identity

## Production

FastAPI serves `frontend/dist/`. After UI changes: `pnpm build` and `pm2 restart litreview-api`.

---

## Design rules

Research-ops dashboard for technical users. Preserve violet accent, glass surfaces, Inter (self-hosted via `@fontsource-variable/inter` in `main.tsx`).

### Token contract

- **Source:** `styles/tokens.css`, `styles/theme-overrides.css`
- No raw hex/rgb/hsl in `.tsx`/`.ts`
- No new `text-zinc-*` / `bg-zinc-*` / `border-zinc-*`
- Use semantic classes: `bg-background`, `text-foreground`, `glass-panel*`, `Badge` variants
- Light and dark parity required

### Component priority

1. `components/ui/*` primitives
2. Glass utilities in `styles/components.css`
3. New semantic tokens
4. One-off classes only when no alternative

### Dial preset

`DESIGN_VARIANCE=4`, `MOTION_INTENSITY=3`, `VISUAL_DENSITY=8`

### Pre-flight (style work)

- [ ] No raw zinc or color literals in changed TSX
- [ ] Both themes render correctly
- [ ] Reduced-motion respected
- [ ] Status dots only for real semantic state
- [ ] Focus, keyboard, loading, error, empty states work
- [ ] No business logic or API contract changes from style edits

---

## UI redesign tracker

| Phase | Name | Status |
|-------|------|--------|
| 0 | Guardrails | Done |
| 1 | Chrome consolidation | Revised (minimal breadcrumb + info strip) |
| 2 | Protocol + Setup | Pending |
| 3 | Live + Gate | Partial (stop confirm, "Needs your input" sidebar group, persisted screening overrides) |
| 4 | Workspace (Data) | Pending |
| 5 | Deliverables | Partial (Results categories, explicit package + download actions, `needs_revision` banner) |
| 6 | Ops + polish | Partial (tab a11y, aria-live status, offline banner, self-hosted Inter) |

**Constraints:** Keep `RunTab` ids, `parseRunUrl`, `RESUME_PHASE_ORDER`, typed API usage, screening gate, export URLs.

---

## Regression checklist

Run before merging changes to `frontend/src/views/` or run navigation.

### Routes and tabs

- [ ] `/` loads Setup
- [ ] `/run/wf-XXXX` defaults to Activity
- [ ] Tabs render Activity, Results, Data, Config, Cost; arrow keys move focus
- [ ] All primary tabs load
- [ ] Legacy `/quality` and `/references` URLs open Results
- [ ] `review-screening` only when `awaiting_review`

### Results

- [ ] Manuscript default when present; export actions work
- [ ] Figures, Quality, Files, References categories
- [ ] `submissionFocusTarget=reference-papers` highlights ZIP row

### Pipeline actions

- [ ] Resume from Activity timeline
- [ ] Stop run shows confirm dialog; "Keep running" cancels
- [ ] Screening overrides survive reload; approve continues workflow
- [ ] `needs_revision` run shows badge + Results banner
- [ ] Package manuscript, then Download submission package
- [ ] SSE on live run
- [ ] Data tab filters

### Build

- [ ] `pnpm test` and `pnpm typecheck`
- [ ] `pnpm build` + `pm2 restart litreview-api` for production

## Testing

- Vitest runs in the node environment by default (no `test` block in `vite.config.ts`).
- Component interaction tests opt in with a first-line `// @vitest-environment jsdom` docblock and `import "@/test/dom"` (jest-dom matchers; cleanup + storage reset after each test).
- Use Testing Library (`@testing-library/react`, `user-event`) with role/label queries. Examples: `components/ui/glass-tabs.test.tsx`, `views/ScreeningReviewView.test.tsx`, `components/run/RunChrome.test.tsx`.
