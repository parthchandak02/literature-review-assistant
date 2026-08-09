# UI Redesign Phases (Tracker)

Canonical tracker for the frontend seamless-UX initiative. Inspired by workflow-first patterns (Elicit protocol page, SciSpace agent workspace, ThesisAI reader, Mobbin B2B dashboards).

**Design constraints:** preserve violet/glass/Inter brand; `frontend` skill; no backend pipeline changes without separate approval.

**Related docs:** `UI_ARCHITECTURE.md` (contracts), `IMPLEMENTATION_STATUS.md` (verification gates), `.cursor/skills/frontend/SKILL.md`.

---

## Phase status

| Phase | Name | Status | Notes |
|-------|------|--------|-------|
| 0 | Guardrails | **Done** | Tracker, tests, UI_ARCHITECTURE, regression checklist (2026-08-09) |
| 1 | Chrome consolidation | **Revised** | Phase chips removed; restored topic breadcrumb + single-line info strip (2026-08-09) |
| 2 | Protocol + Setup | Pending | Wizard setup, draft full-page protocol |
| 3 | Live + Gate | Pending | Unified live feed, screening gate prominence |
| 4 | Workspace (Data) | Pending | Papers table workspace, outcomes sub-view |
| 5 | Deliverables | Partial | Results category nav shipped; left-rail + reader shell remain |
| 6 | Ops + polish | Pending | Cost dedup, HLJS tokens, a11y |

Update the **Status** column when a phase ships. Link PRs in **Notes** when helpful.

---

## Phase 0: Guardrails (no layout changes)

**Goal:** Lock contracts and manual regression path before further UI refactors.

### Deliverables

- [x] This tracker (`UI_REDESIGN_PHASES.md`)
- [x] Results categories documented in `UI_ARCHITECTURE.md`
- [x] Frontend UI regression checklist (below)
- [x] Vitest: `parseRunUrl` legacy aliases + all `RunTab` values
- [x] Vitest: Results category defaults and resolution (`frontend/src/lib/resultsCategories.ts`)
- [x] `IMPLEMENTATION_STATUS.md` gate for frontend UI work

### Exit criteria

- `cd frontend && pnpm test && pnpm typecheck` pass
- No user-visible layout changes in Phase 0 PR
- Manual smoke on one completed run (checklist below)

---

## Frontend UI regression checklist

Run before merging any phase that touches `frontend/src/views/` or run navigation.

### Routes and tabs

- [ ] `/` loads Setup (new review)
- [ ] `/run/wf-XXXX` defaults to Activity tab
- [ ] Each primary tab loads: `config`, `activity`, `database`, `cost`, `results`
- [ ] Legacy URLs `/run/wf-XXXX/quality` and `/references` redirect to Results tab
- [ ] `review-screening` tab appears only when status is `awaiting_review`

### Results deliverables

- [ ] Completed run: default category is Manuscript when manuscript exists, else Files
- [ ] Manuscript viewer loads; export actions visible (.tex, DOCX, Submission Package when packaged)
- [ ] Figures: PRISMA + custom diagrams + figure files
- [ ] Quality: GRADE table + evidence network (when run has export id)
- [ ] Files: PROSPERO downloads + artifact groups; Reference papers ZIP row present
- [ ] References: embedded list; **Reference papers ZIP** downloads (not deep-link only)
- [ ] `submissionFocusTarget=reference-papers` opens Files category and highlights ZIP row

### Pipeline actions (must not break)

- [ ] Resume from Activity timeline (historical failed run)
- [ ] Screening review: override + approve continues workflow
- [ ] Manuscript export / submission package generation
- [ ] SSE activity stream updates on live run
- [ ] Data tab: papers table loads, filters apply

### Build

- [ ] `cd frontend && pnpm typecheck`
- [ ] `cd frontend && pnpm test`
- [ ] After production-bound changes: `pnpm build` and `pm2 restart litreview-api`

---

## Phase 1-6 summaries (execution backlog)

### Phase 1: Chrome consolidation

Keep run chrome minimal: topic in App breadcrumb; single-line status/meta/funnel strip; tabs below. Phase progress lives only on Activity (timeline + log). No duplicate phase chips in the header.

**Primary files:** `RunView.tsx`, `App.tsx`.

**Do not change:** `RunTab` ids, API calls, resume behavior.

### Phase 2: Protocol + Setup

ThesisAI-style setup wizard; draft config without full 5-tab shell; Elicit-style protocol summary on Config tab.

### Phase 3: Live + Gate

SciSpace-style unified live feed; screening gate visible on workflow stepper when `awaiting_review`.

### Phase 4: Workspace (Data)

SciSpace-style papers table with column picker and CSV export; Papers | Outcomes sub-views.

### Phase 5: Deliverables (remaining)

Linear-style left rail inside Results; `ReaderShell` for manuscript; quality links to Data.

### Phase 6: Ops + polish

Cost tab vs Settings dedup; token-backed HLJS; empty/error states; a11y on glass tabs.

---

## Contract preservation (all phases)

- Keep `RunTab` route segments and `parseRunUrl` behavior
- Keep `RESUME_PHASE_ORDER` aligned with `src/orchestration/resume.py`
- Keep typed API usage via `frontend/src/lib/api.ts`
- No YAML config UI that cannot round-trip to `config_snapshot.yaml`
- No removal of human screening gate or export/download URL contracts

---

## Changelog

| Date | Change |
|------|--------|
| 2026-08-09 | Phase 1 revised: removed phase chips; restored minimal breadcrumb + info strip |
| 2026-08-09 | Phase 0 complete: tracker, category tests, regression checklist |
