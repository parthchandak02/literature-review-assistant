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
`review-screening` appears when status is `awaiting_review` and is placed second, directly after Activity (`orderRunTabs` in `components/run/runRouting.ts`).

Tabs use `GlassTabs variant="underline"` (content-width, left-aligned). "Download submission package" sits on the same row, right-aligned.

`GlassTabs` is an ARIA tablist: roving focus with Arrow Left/Right, Home, End; each tab `aria-controls` the `tabpanel-{id}` region in `RunView.tsx`.

**Auto-routing** (`resolveAutoRouteTab` / `defaultTabForStatus` in `components/run/runRouting.ts`): when a run is opened on the default tab (Activity), `config_ready` and `awaiting_prospero` switch to Config and `awaiting_review` switches to `review-screening`. This runs once per run and gate. It is skipped for the workflow named in the page-load URL when that URL has an explicit tab (`/run/{id}/{tab}`), so deep links keep working. `parseRunUrl` is unchanged. Users can leave the gate tab freely.

## Results categories

Logic in `lib/resultsCategories.ts` (vitest-covered):

| Id | When shown |
|----|------------|
| `manuscript` | `doc_manuscript` exists |
| `figures` | PRISMA/custom diagrams |
| `quality` | Run has export id |
| `files` | Always |
| `references` | Always |

Default: Manuscript if present, else Files. `#audit-findings` in the URL (`categoryForHash`) opens Quality and scrolls to the audit block.

**Locked state** (`lockedResultsState`): before results exist, Results shows a lock with a CTA to Activity. For `awaiting_review` it says "Waiting on your screening review" with a CTA to `review-screening`, even when history outputs exist. Any files produced so far are listed under "Files so far".

**Manuscript** (`ManuscriptViewer.tsx`):

- Text column capped at 68ch (`.manuscript-prose` in `styles/manuscript.css`); the page scroll carries the document, with no inner scroller. The toolbar is sticky
- On `lg`, a sticky left outline rail built from the rendered heading ids, with IntersectionObserver scroll-spy (`tocScrollSpy.ts`) and `aria-current="location"`. Below `lg`, an Outline dropdown that closes after a jump. No Outline control when there are no headings
- Zoom buttons are labelled; clicking the percentage resets to 100%
- A "Draft quality" chip appears when `detectTemplateText` (`draftQuality.ts`) finds template or placeholder text; its menu lists each match with an excerpt
- Tables are wrapped in `overflow-x-auto`. Missing figures render a dashed "Figure not found: {alt}" placeholder (`ManuscriptImage.tsx`). Print hides the toolbar and rail and unclamps the run tab panel

**Submission package** (`submissionPackage.ts`): one per-run state machine shared by the Manuscript actions and the chrome `SubmissionPackageButton`:

| State | Offered action |
|-------|----------------|
| `unbuilt` | Build (`force=false`) |
| `building` | none (busy) |
| `incomplete` (409 or partial `submission/`) | Rebuild (`force=true`), no confirm |
| `ready` | Download; Rebuild asks for confirmation because it overwrites the ZIP |
| `error` | Retry with the failed attempt's `force` |

The chrome "Download submission package" runs `ensureSubmissionPackage`: Build, auto-Rebuild on 409, then download. A `ready` package downloads without rebuilding. Export URLs are unchanged.

**Figures and Files**: figure cards (`FigureCard.tsx`) share download, "Preview unavailable" on load error, 4:3 thumbnails and click-to-zoom. Custom diagrams show real planned/saved counts from the brief pack or generation report. Previewable file rows use a toggle button with `aria-pressed`, separate from the download link.

**Quality**: "Audit findings" (`AuditFindingsBlock.tsx`, anchor `#audit-findings`) is first. Data comes from `GET /api/run/{run_id}/manuscript-audit`: contract violations plus audit findings, sorted failures → warnings → notes with severity badges. With no audit record it links to `run_summary.json` and Files. The `needs_revision` banner's "View audit findings" opens it. Then GRADE and the evidence network (keyboard-reachable nodes, a right-column inspector on `lg`, cluster legend, arrows on citation edges only, and colours inlined on SVG export).

**References**: search (title, author, year, DOI, database), a "Full text only" toggle, and Clear filters (`referenceFilters.ts`). Titles are decoded with `decodeHtmlEntities`. Icon actions have `aria-label`s, and PDF fetch progress is a `role="progressbar"`.

## Run chrome

- Topic breadcrumb in App bar
- Single-line info strip, outcome first: status, outcome ("6 included of 1,716 records"), cost (neutral, 2 decimals, links to Cost), a "Funnel" popover with the full funnel as a vertical list, date, and a de-emphasised workflow id with a copy icon button ("Copied" announced via an sr-only live region; failures show an error toast). Separators are `aria-hidden` dividers, not literal characters
- Underline `GlassTabs` below the strip, with the package download on the same row
- "Waiting on you" banner (`RunGateBanner.tsx`, `role="status"`) below the chrome on every tab except the gate's action tab, for `config_ready` / `awaiting_prospero` (action tab Config) and `awaiting_review` (action tab `review-screening`). It states what is needed and has a primary CTA that switches to the action tab
- Phase timeline on Activity tab only (no duplicate header chips)
- Run status announced via `aria-live="polite"` in `RunChrome.tsx`
- Finished runs show "Download submission package" (`SubmissionPackageButton`) in the chrome. It shares the submission package state machine with the Results Manuscript actions (see Results categories)
- `needs_revision` status (contracts/audit failed, artifacts produced) has its own label/badge and a Results banner (`isNeedsRevisionStatus` in `lib/constants.ts`)

## Sidebar

- Settings, theme toggle and the collapse button share one fixed footer row at the bottom, in both expanded and collapsed modes. The collapse tooltip shows the shortcut (Cmd/Ctrl+B). The shortcut is ignored while focus is in an input, textarea, select or contenteditable
- Groups (`partitionHistory` / `laneOf` in `hooks/useSidebarRuns.ts`):
  - "Needs your input": `config_generating`, `config_ready`, `awaiting_prospero`, `awaiting_review`
  - "In progress": every other visible review
  - "Completed": `is_completed_hidden`, or a finished (`done`) review with no live run, unless the user chose "Move to In progress". That choice is kept in `localStorage` (`sidebar-in-progress-pins`) because the API cannot tell "never filed" from "restored"
  - "Archived": `is_archived`
- Use the noun "review" in all sidebar copy. Empty lanes read "No completed reviews" / "No archived reviews". Lane toggles set `aria-expanded`. In collapsed mode the lanes show as icons with count badges, and `#NN` badges are tinted by status (`STATUS_VARIANT`)
- `RunNavCard` has no nested interactive elements. The title is the single select button, and its `::after` overlay covers the card. Stop, Resume, the actions menu, the details toggle, copy-id and the note field are siblings above it (`relative z-10`)
- A card shows the title (3 lines, full title in a tooltip), status, one key metric and the date. The metric is hidden until search has found records. Funnel, cost and workflow id sit behind the metric's details toggle
- Status text comes from `runStatusLabel`; caps are CSS only
- A card that cannot be opened shows why ("No database yet") as a subtitle and in its tooltip
- The actions menu (`DropdownMenu`) holds Add note, Move to In progress, Move to Completed, Archive and, for archived reviews, Delete permanently
- Archive and the Move to... actions apply at once, then show a sonner toast with Undo that restores the previous lane
- Stop and Delete use `ConfirmDialog`. It shows `onConfirm` errors inline (`role="alert"`) and stays open. The delete dialog names the review and #id and lists what is removed: the run directory (database, manuscript, figures, submission package, PDFs, logs and artifacts) and the registry row
- Mobile: the sidebar is a left `Sheet` (dialog role, focus trap, Esc). Focus returns to "Open menu" on close
- Resize handle: `role="separator"` with `aria-valuenow`; arrow keys step 16px (Shift 64px), Home/End jump to 200/420, and double-click resets to 240

## Setup and state

- API keys panel never receives server secrets; server-set keys show "Configured on server" (from `/api/config/env-keys/status`)
- Screening overrides persist per workflow in `sessionStorage` (`hooks/useScreeningReview.ts`)
- Offline banner ("Can't reach the server", Retry now) in `App.tsx`; suppressed while streaming. Operator hints (`/api/health`, `pm2 status`) render only in dev builds
- App bar question title is plain text (full text in a tooltip) with a separate "Copy question" icon button. Toasts sit bottom-right
- `AppErrorBoundary` offers "Reload this page" and "Go home", with the raw message under "Technical details". `ViewBoundary` offers "Try again", "Reload page" and "Copy details"
- Settings dialog uses `GlassTabs`, resets to `initialTab` on every open, and sizes per tab (about 560px for API keys, wide for Global costs)
- API keys: required providers first, the rest under a collapsed "Optional providers". Known prefixes get a format hint and a soft warning (`lib/apiKeyFields.ts`). Each key has Clear; a debounced "Saved" tick confirms the browser save. Email fields are `type=email` with no reveal toggle
- Global costs (`CostsPanel.tsx`) keep the previous data dimmed while refreshing; counts use "Reviews"

## Activity log

- `LogStream.tsx` virtualises with `@tanstack/react-virtual` (measured rows, `anchorTo: "end"`). A "current phase" header sits outside the list once its separator scrolls away
- Follow mode pauses when the user scrolls up; a "N new events" pill jumps to the latest and resumes follow (`lib/logFollow.ts`)
- Severity chips in `ActivityLogPanel.tsx`: All, Warnings+, Errors, Decisions (`filterEventsBySeverity` in `lib/logLine.ts`; `phase_start` is kept for grouping)
- The log region is `aria-live="off"`; a separate polite region announces only phase changes and errors
- Rows use `text-xs leading-5` and `[overflow-wrap:anywhere]`. Tags show `humanizeLogTag(tag).label` with the glossary description as `title`. Rows stack timestamp and tag above the message below the `@md` container width
- `eventToLogEntry` returns `ts`, `tag`, `message` and optional `detail` (full reason, full model path, full title) shown on row expand. Routine status lines are muted; amber is for `warn`

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

| Token | Use |
|-------|-----|
| `bg-intent-*-solid` / `text-intent-*-solid-fg` | Solid fills (buttons, active segments); text on them is >= 4.5:1 |
| `text-intent-*-text` | Readable text on `bg-intent-*-subtle` (badges, alerts) |
| `border-border-strong` | Borders that must meet 3:1 (inputs, focus-adjacent edges) |
| `ring-ring` | Focus rings |
| `bg-scrim` | Modal/sheet/drawer backdrops (`--color-scrim`) |
| `text-2xs` | 11px, the minimum text size. Scale: `2xs`, `xs`, `sm`, `base`, `lg` |
| `rounded-control` / `rounded-panel` / `rounded-pill` | Inputs and buttons / cards, dialogs, popovers / chips and badges |

`rounded-full` stays for circles (dots, avatars, steppers). Chart tick `fontSize` is 11 minimum.

### Button sizes

Use the `size` prop, never a height class in `className`.

| Size | Height |
|------|--------|
| `xs` | h-7 (dense rows, inline actions) |
| `sm` | h-8 |
| `default` | h-9 |
| `lg` | h-10 (primary CTAs) |
| `icon` / `icon-sm` | h-9 w-9 / h-8 w-8 |

### Lint guardrails

`frontend/eslint.config.js` (`no-restricted-syntax`, error) rejects:

- Arbitrary font sizes (`text-[Npx]`)
- `outline-none` without a `ring-*` or `outline-*` replacement in the same class string
- A height class (`h-N`) in `<Button className>`

A real exception needs `// eslint-disable-next-line no-restricted-syntax -- <reason>`.

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

Item-level status for the current redesign: [docs/ux/TRACKER.md](ux/TRACKER.md).

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
- [ ] Manuscript: 68ch column, sticky toolbar, outline rail tracks scroll on `lg`
- [ ] `awaiting_review` Results says "Waiting on your screening review"
- [ ] Quality shows Audit findings first

### Pipeline actions

- [ ] "Resume from…" menu on Activity; confirm lists re-run phases and prior spend
- [ ] Stop run shows confirm dialog; "Keep running" cancels
- [ ] Screening overrides survive reload; approve continues workflow
- [ ] `needs_revision` run shows badge + Results banner
- [ ] Build submission package, then Download; Rebuild asks to confirm
- [ ] SSE on live run
- [ ] Data tab filters

### Build

- [ ] `pnpm test` and `pnpm typecheck`
- [ ] `pnpm build` + `pm2 restart litreview-api` for production

## Testing

- Vitest runs in the node environment by default (no `test` block in `vite.config.ts`).
- Component interaction tests opt in with a first-line `// @vitest-environment jsdom` docblock and `import "@/test/dom"` (jest-dom matchers; cleanup + storage reset after each test).
- Use Testing Library (`@testing-library/react`, `user-event`) with role/label queries. Examples: `components/ui/glass-tabs.test.tsx`, `views/ScreeningReviewView.test.tsx`, `components/run/RunChrome.test.tsx`.
