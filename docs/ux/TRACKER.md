# UX Redesign Tracker

Source audit: [UX_AUDIT_2026-09-28.md](../UX_AUDIT_2026-09-28.md). Plan: 6 sprints, commit to `main` once per sprint.

**Status values:** `todo`, `wip`, `done`, `wontfix`, `blocked:<question>`. Agents update the row they close and fill in the Commit column.

**Sprint map:**
- 1 = Foundation (DS)
- 2 = Status and safety (ACT, SHL-sidebar, BE)
- 3 = Screening (SCR)
- 4 = Data and Cost (DAT, CST)
- 5 = Results (RES)
- 6 = Setup, Shell, Log (SET, SHL-shell, LOG)

Note: sidebar SHL rows run in Sprint 2 and app-shell and settings rows in Sprint 6. Each row's Sprint column is authoritative.

| ID | Sev | Where | Issue | Fix | Sprint | Status | Commit |
|---|---|---|---|---|---|---|---|
| BE-01 | H | wf-0003 Activity | Error event emitted for config_ready gate status | Don't emit error event for gate statuses | 2 | done | fbf8640 |
| ACT-01 | H | wf-0003 Activity | config_ready run lands on Activity, not Config | Route config_ready to Config tab | 2 | done | sprint-2 |
| ACT-02 | H | Run chrome funnel strip | The strip reads `1,716 retrieved > 1,548 deduped > … > 6 inclu` and cuts off the **one number users care about**. It is 11px mono with seven colours and `>` separators. | Lead with the outcome: **"6 included"** from 1,716 records. Put the full funnel in a hover popover or the PRISMA figure. | 2 | done | sprint-2 |
| SHL-01 | H | Sidebar | Completed run #1 sits under "Reviews", while the **"Completed (0)"** lane is empty. The information architecture contradicts itself. | Auto-file completed runs into Completed, or drop the lane and use a status filter. | 2 | done | sprint-2 |
| SHL-02 | M | Sidebar cards | #2 and #3 both read "What hospital-based and…". Two truncated lines make them indistinguishable. Config-state cards show "0 found → 0 included", which is noise. | Give titles three lines or a smart abbreviation, show the full title on hover, and hide the funnel until search has run. | 2 | done | sprint-2 |
| BE-02 | M | Data table | `students&amp;apos;` shows **undecoded HTML entities**. Country, Full-text, Primary Status ("unknown") and RoB Source are empty or "--" for nearly every row. | Decode entities at ingest. Auto-hide columns with no data and add a Columns toggle. | 2 | done | fbf8640 |
| BE-03 | M | Manuscript | Abstract template leakage (content pipeline) | Detect/replace template text in abstract writer | 2 | done | fbf8640 |
| RES-01 | M | Manuscript | Manuscript measure ~150ch; no draft-quality chip | 68ch column; warning chip on template text | 5 | done | sprint-5 |
| CST-01 | M | Cost chart | Raw labels such as "Phase 6f Custom Diagram Drawing" wrap to four lines. The top bar is **grey** while smaller ones are orange or red, so colour emphasis is inverted. | Use short human labels, one hue, and highlight the top bar. | 4 | done | sprint-4 |
| ACT-03 | M | Run tabs | Five equal full-width tabs (about 230px each, 38px tall) create a heavy band above every view. | Use underline tabs with left-aligned, content-width items, and move the Download CTA onto the same row on the right. | 2 | done | sprint-2 |
| ACT-04 | L | Stepper | The connectors are tiny "–" glyphs, not lines. All-complete and all-pending states look alike in weight. | Use 2px connector lines filled with progress colour, and the sub-status text from S1. | 2 | done | sprint-2 |
| SET-01 | L | Setup | A 3-button quiz floats in empty space. There's no title, and the research-question input is hidden behind the quiz. | Put an h1 and a big question textarea first. Offer review type as two cards, with "Help me decide" as a link. | 6 | done | sprint-6 |
| SET-02 | H | `views/ConfigView.tsx:243-256`, `setup/QuestionStage.tsx:260-268` | "Paste YAML" is offered, but launch is then disabled for pasted configs, so the path is a dead end. | Support launching pasted YAML, or relabel the action "View YAML (no launch)". | 6 | done | sprint-6 |
| SET-03 | H | `config/ProsperoGatePanel.tsx:184-199` | There's no path forward without a PROSPERO CRD, and scoping reviews are forced through the same gate. | Add "Start without registration". Skip or relabel the gate for scoping reviews (OSF). | 6 | done | sprint-6 |
| SET-04 | H | `setup/ReviewTypeDecisionStage.tsx:84-118` | Experts must take the quiz. The step count isn't shown, and there's no Back. | Show two type cards plus a "Help me decide" link, "Step n of 4", and Back. | 6 | done | sprint-6 |
| SET-05 | M | `ReviewTypeDecisionStage.tsx:105` | Uses the jargon "IEDO". | Use plain words. | 6 | done | sprint-6 |
| SET-06 | M | `QuestionStage.tsx:149-162` | The textarea has no label, and the page has no h1. | Add a visible "Research question" label and an h1. | 6 | done | sprint-6 |
| SET-07 | M | `QuestionStage.tsx:99-104,176` | Missing-key errors appear only after submit, and there's no link to Settings. | Check up front, name the provider, and add an "Open Settings → Keys" link. | 6 | done | sprint-6 |
| SET-08 | M | `QuestionStage.tsx:167-172` | The "Retry" button only dismisses the error. | Label it "Dismiss" or make it actually retry. | 6 | done | sprint-6 |
| SET-09 | M | `QuestionStage.tsx:185-211` | Options sit below the primary CTA. | Move options above the CTA. | 6 | done | sprint-6 |
| SET-10 | L | `QuestionStage.tsx:216-257` | "Reuse past config" menu: no Esc, no aria-expanded, capped at 10 runs, and invisible when empty. | Use Radix Popover with search, and add an empty hint. | 6 | done | sprint-6 |
| SET-11 | M | `setup/CsvDropZone.tsx:136-146` | The drop zone can't be reached by keyboard. | Use a `<label htmlFor>` or a button. | 6 | done | sprint-6 |
| SET-12 | M | `CsvDropZone.tsx:27-38` | `.CSV` files are silently rejected and parse errors are swallowed. | Match case-insensitively and show an inline error. | 6 | done | sprint-6 |
| SET-13 | M | `CsvDropZone.tsx:80-132` | The major consequence of "master list" (it skips search) is explained only in a tooltip. | Show the consequence text inline, and use RadioGroup. | 6 | done | sprint-6 |
| SET-14 | M | `ConfigView.tsx:95-111`, `setup/constants.ts` | The stepper shows made-up history, "PICO" appears for scoping reviews, and labels like "Routing" and "Backup" are unclear. | Hide the stepper when provenance is unknown, use PCC for scoping reviews, and use plain labels. | 6 | done | sprint-6 |
| SET-15 | M | `ConfigView.tsx:78,236`, `YamlEditor.tsx` | YAML edits are lost when switching tabs, there's no dirty flag, reset or parse validation, and the editor has a fixed 400px height. | Lift state up, add a dirty dot, Reset, inline YAML errors and a viewport height. | 6 | done | sprint-6 |
| SET-16 | L | `ProsperoGatePanel.tsx:81-137` | An invalid CRD just disables the button without saying why. | Add helper text ("CRD42 + digits") and an error on blur. | 6 | done | sprint-6 |
| SHL-03 | H | `App.tsx:131`, `Sidebar.tsx:167-190` | The mobile drawer has no focus trap, no Esc and no dialog role. | Use the Sheet primitive. | 2 | done | sprint-2 |
| SHL-04 | H | `sidebar/RunNavCard.tsx:450-481`, `RunCardMetrics.tsx` | Buttons are nested inside the card `<button>`, and Space triggers both. | Build the card with an overlay link and sibling actions. | 2 | done | sprint-2 |
| SHL-05 | H | `RunNavCard.tsx:255-368` | Archive and Complete fire instantly on 28px icons that sit next to Resume. | Show a toast with Undo, and move these actions into the overflow menu. | 2 | done | sprint-2 |
| SHL-06 | M | `DeleteConfirmDialog.tsx:20` | The dialog says "Delete this review?" without naming which review, and it doesn't say what gets deleted. | Name the topic and #id, list what gets removed, and label the button "Delete permanently". | 2 | done | sprint-2 |
| SHL-07 | M | `ConfirmDialog.tsx:38-47` | When `onConfirm` throws, the error is swallowed. | Show the error inline. | 2 | done | sprint-2 |
| SHL-08 | M | `RunNavCard.tsx:147-176` | The hand-rolled overflow menu has no Esc and no outside-click close, and it gets clipped. | Use Radix DropdownMenu. | 2 | done | sprint-2 |
| SHL-09 | M | `RunNavCard.tsx:369-426` | Two different actions are both labelled "Restore" with the same icon. | Name the destination ("Move to In progress"). | 2 | done | sprint-2 |
| SHL-10 | M | `RunNavCard.tsx:119-138` | Disabled cards at 50% opacity give no reason. | Add a tooltip with the reason. | 2 | done | sprint-2 |
| SHL-11 | M | `RunNavCard.tsx:525` | The empty note field appears only on hover, so touch users never see it. | Add an "Add note" item to the overflow menu. | 2 | done | sprint-2 |
| SHL-12 | M | `SidebarCompletedArchivedSection.tsx:56`, `WorkflowBadges.tsx` | In collapsed mode the lanes vanish and bare "#NN" badges are left. | Use lane icons with counts and status-tinted badges. | 2 | done | sprint-2 |
| SHL-13 | L | `SidebarCompletedArchivedSection.tsx:81,128` | Copy mixes "runs", "chats" and "reviews", and the lanes lack aria-expanded. | Use one noun: **review**. Add aria-expanded. | 2 | done | sprint-2 |
| SHL-14 | L | `SidebarInProgressSection.tsx:110-133` | The group is labelled "Reviews", but everything is a review. | Rename it "In progress". | 2 | done | sprint-2 |
| SHL-15 | L | `Sidebar.tsx:314` | The resize handle works only with a mouse. | Add `role=separator`, arrow keys, and double-click to reset. | 2 | done | sprint-2 |
| SHL-16 | L | `SidebarHeader.tsx:72` | Settings and theme move or vanish when the sidebar collapses. | Keep one fixed location. | 2 | done | sprint-2 |
| SHL-17 | L | `RunNavCard.tsx:488` | "RECONNECTING" is hard-coded in caps. | Use `statusLabel` with the caps style applied in CSS. | 2 | done | sprint-2 |
| SHL-18 | M | `App.tsx:432-441` | Clicking the title silently copies it. | Add an explicit copy icon and make the title plain text. | 6 | done | sprint-6 |
| SHL-19 | M | `App.tsx:397-404` | The offline banner tells users about `pm2 status`. | Keep a user message and put operator hints behind a dev flag. | 6 | done | sprint-6 |
| SHL-20 | M | `App.tsx:55-66` | The error boundary shows a raw message, and "Reload" goes to `/` and loses context. | Offer "Reload this page" and "Go home", with collapsible details. | 6 | done | sprint-6 |
| SHL-21 | L | `App.tsx:204` | Cmd+B fires inside textareas and isn't discoverable. | Ignore it in editable fields and show it in the tooltip. | 6 | done | sprint-6 |
| SHL-22 | L | `App.tsx:356` | Toasts at top-center cover the breadcrumb. | Move them to bottom-right. | 6 | done | sprint-6 |
| SHL-23 | M | `SettingsDialog.tsx:47-67` | Tabs have no ARIA roles and the `initialTab` prop is ignored. | Reuse GlassTabs and reset on open. | 6 | done | sprint-6 |
| SHL-24 | M | `SettingsDialog.tsx:31` | The dialog is always 1280px wide, so key inputs stretch. | Use a width per tab. | 6 | done | sprint-6 |
| SHL-25 | M | `ApiKeysSection.tsx:22-135` | Saving on every keystroke gives no feedback, there's no clear button or format check, and nine providers are listed flat. | List required providers first, collapse "Optional", add format hints, a Saved tick and a Clear button. | 6 | done | sprint-6 |
| SHL-26 | L | `ApiKeysSection.tsx:96,172` | Email fields are masked as passwords, and the warning has no icon. | Use `type=email` and add an alert icon. | 6 | done | sprint-6 |
| SHL-27 | L | `GlobalCostOpsDialog.tsx` | Dead code, and "Workflows" wording; the layout jumps on reload. | Delete it, and keep stale data dimmed while refreshing. | 6 | done | sprint-6 |
| SHL-28 | L | `ViewBoundary.tsx:46` | "Try again" remounts into the same crash. | Add "Reload page" and "Copy details". | 6 | done | sprint-6 |
| ACT-05 | H | `activity/PhaseTimeline.tsx:67`, `ui/HorizontalStepper.tsx:119` | Seven milestones only, with sub-phase, progress and elapsed time never shown. | Show "Full-text retrieval · 34/120 · 6m" under the active step and mirror it in the chrome. | 2 | done | sprint-2 |
| ACT-06 | H | `ActivityView.tsx:192-208` | Resume is a hidden double-tap that silently disarms after 8s and re-runs paid phases. | Add an explicit "Resume from…" menu and a confirm listing the phases and prior cost. | 2 | done | sprint-2 |
| ACT-07 | H | `RunView.tsx:159`, `RunChrome.tsx:190` | `awaiting_review` gets no redirect or banner, and its tab sits last. | Show a "Paused: 312 decisions need you → Review" banner on every tab and put the tab second. | 2 | done | sprint-2 |
| ACT-08 | M | `ActivityView.tsx:148-166` | `resumeBlockedReason` is computed but never shown. | Show it as an inline hint. | 2 | done | sprint-2 |
| ACT-09 | M | `ActivityView.tsx:224` | The failure banner shows the *first* error, has no role=alert, and offers no action. | Show "Failed in {phase}" with the last error, "Show in log" and "Resume from {phase}". | 2 | done | sprint-2 |
| ACT-10 | M | `lib/constants.ts:335` | Unknown statuses fall back to "Ready" (stale runs, config_generating). | Map through `STATUS_LABEL`. | 2 | done | sprint-1 |
| ACT-11 | M | `HorizontalStepper.tsx:95-139` | State is conveyed by colour and icon only, with no `aria-current` and no `<ol>`. | Add sr-only status text. | 2 | done | sprint-2 |
| ACT-12 | L | `ActivityView.tsx:57,90` | "Start the server" is developer copy. | "Can't reach the server. Retry". | 2 | done | sprint-2 |
| ACT-13 | L | `RunChrome.tsx:91-125` | Literal ` | ` and `>` separators are read aloud, "Copied" isn't announced, and cost is styled as a warning. | 2 | done | sprint-2 |
| LOG-01 | H | `LogStream.tsx:328-380` | Virtualisation assumes 24px rows, but rows wrap, which breaks scroll and sticky phase headers above 350 rows. | Use `@tanstack/react-virtual` with measured rows and a sticky phase header outside the list. | 6 | done | sprint-6 |
| LOG-02 | H | `LogStream.tsx:299`, `ActivityLogPanel.tsx` | Follow stops silently, and there's no severity filter. | Add a "↓ 14 new" pill and chips: All, Warnings+, Errors, Decisions. | 6 | done | sprint-6 |
| LOG-03 | M | `LogStream.tsx:365` | `aria-live` on a firehose floods screen readers. | Announce only phase changes and errors. | 6 | done | sprint-6 |
| LOG-04 | M | `LogStream.tsx:370-442` | Text is 10–11px with `break-all`, which splits DOIs mid-word. | Use a 12px floor, `overflow-wrap:anywhere` and `leading-5`. | 6 | done | sprint-6 |
| LOG-05 | M | `LogStream.tsx:425` | Decision cards drop their timestamp and break the grid. | Keep them in the 3-column grid. | 6 | done | sprint-6 |
| LOG-06 | M | `lib/logLine.ts` (8 sites) | Jargon: `PROG phase_2_search`, `SRCHOV`, `rob=`, raw `ev.type`, and full model paths (`accounts/fireworks/models/…`). | Use human tags, `PHASE_LABELS`, "risk of bias" and short model names. Move full detail into row expand. | 6 | done | sprint-6 |
| LOG-07 | L | `LogStream.tsx:163` | Routine status lines are amber italic, which causes warning fatigue. | Use muted styling, and keep amber for `warn` only. | 6 | done | sprint-6 |
| LOG-08 | L | `logLine.ts:259` | Reasons are cut at 95 characters with no ellipsis. | Add "…" and row expand. | 6 | done | sprint-6 |
| LOG-09 | L | `ActivityLogPanel.tsx:77` | An empty search result shows the "no events yet" copy, and the search box has no aria-label. | Show "No events match 'q'" with Clear. | 6 | done | sprint-6 |
| SCR-01 | H | `screening/ScreeningFiltersBar.tsx:23` | There's no Exclude filter, no search and no confidence sort, so false negatives can't be rescued. | Add Exclude, Overridden, search, and a "confidence ↑" sort. | 3 | done | sprint-3 |
| SCR-02 | H | `ScreeningPaperRow.tsx:74-133` | Each decision takes three clicks, with no keyboard shortcuts and no bulk actions. | Inline I/E toggles, j/k, i/e, u (undo), Enter (expand), and checkbox bulk actions. | 3 | done | sprint-3 |
| SCR-03 | H | `ScreeningApprovalBar.tsx:30`, `ScreeningReviewView.tsx:26` | A one-way paid gate sits at the top, styled as a warning, with no summary. It doesn't say what happens to Uncertain papers. | Use a sticky footer with a primary button and a summary confirm ("N in, M uncertain → treated as X, K overrides"). | 3 | done | sprint-3 |
| SCR-04 | M | `ScreeningPaperRow.tsx:18` | The reason field isn't seeded from the saved override, so typing overwrites it. | `useState(override?.reason ?? "")`. | 3 | done | sprint-3 |
| SCR-05 | M | `ScreeningPaperRow.tsx:58,85` | The abstract is clamped at 6 lines, so reviewers can't read the evidence. | Unclamp it when expanded. | 3 | done | sprint-3 |
| SCR-06 | M | `ScreeningPaperRow.tsx:112` | "Force Include" is offered on papers already included. | Offer only the opposite action. | 3 | done | sprint-3 |
| SCR-07 | M | `ScreeningReviewView.tsx:83`, `useRunGateActions.ts:102` | If approve succeeds and resume fails, the UI says "Approval failed" and retrying re-posts. | Separate the two states; retry calls resume only. | 3 | done | sprint-3 |
| SCR-08 | M | `screeningBadges.tsx:31` | Low confidence uses the same red as Exclude. | Show confidence as a neutral meter. | 3 | done | sprint-3 |
| SCR-09 | L | `ScreeningPaperRow.tsx:40-107`, `ScreeningApprovalBar.tsx:44` | No aria-expanded, a raw stage id, a lowercase badge, and "active learning" jargon. | Humanise these and add the ARIA attributes. | 3 | done | sprint-3 |
| SCR-10 | L | `ScreeningSummaryHeader.tsx` | Static copy with no counts or progress. | Show "12 of 480 reviewed · 5 overridden" and the thresholds. | 3 | done | sprint-3 |
| RES-02 | H | `constants.ts:463`, `ResultsView.tsx:238-300` | `needs_revision` says "see Results > Quality", but Quality has no audit findings, so the CTA leads nowhere. | Add an "Audit findings" block at the top of Quality and deep-link to it. | 5 | done | sprint-5 |
| RES-03 | M | `ManuscriptActions.tsx:132-200`, `SubmissionPackageButton.tsx` | Two packaging flows use five different verbs, and "Refresh" silently rebuilds. | Use one name and one state machine: "Submission package → Build / Rebuild / Download". | 5 | done | sprint-5 |
| RES-04 | M | `ResultsView.tsx:190` | The Lock says "available once complete" even while paused at screening with artefacts ready. | Show "Waiting on your screening", and show partial Files. | 5 | done | sprint-5 |
| RES-05 | M | `ManuscriptViewer.tsx:150`, `manuscript.css:7` | `prose max-w-none` gives about 150 characters per line, plus double scrollbars from the 70vh inner scroller. | Cap at 68ch, use page scroll and a sticky toolbar. | 5 | done | sprint-5 |
| RES-06 | M | `ManuscriptViewer.tsx:78-147` | The outline overlay covers the text, has no scroll-spy, and shows even with no headings. | Use a sticky left TOC rail on `lg` with `aria-current`. | 5 | done | sprint-5 |
| RES-07 | L | `ManuscriptViewer.tsx:102` | The "-" and "+" zoom buttons have no labels and no reset. | Add aria-labels and click % to reset. | 5 | done | sprint-5 |
| RES-08 | L | `manuscript.css:83` | Print truncates at 70vh, and tables have no overflow wrapper. | Target the scroll container and wrap tables. | 5 | done | sprint-5 |
| RES-09 | M | `ManuscriptImage.tsx:6` | A missing figure renders `null` and silently disappears from the submission. | Show a dashed "Figure not found: {alt}" placeholder. | 5 | done | sprint-5 |
| RES-10 | M | `CustomDiagramsCard.tsx:74,117,125` | A hard-coded "3 planned", no download or zoom, and copy pointing to a non-existent "Artifacts" tab. | Use real counts, reuse FigureGridCard, and say "Files". | 5 | done | sprint-5 |
| RES-11 | L | `ArtifactFileList.tsx:66-129` | "Not generated" appears on any load error, square thumbnails crop plots, and a link is nested inside a role=button. | Say "Preview unavailable", use 4:3 thumbnails, and add aria-pressed. | 5 | done | sprint-5 |
| RES-12 | M | `ReferencesView.tsx:166-384` | The legend matches nothing on the cards, icon-only actions have no aria-label, and there's no search or sort. | Remove the legend, add labels and search, and add a "full text only" filter. | 5 | done | sprint-5 |
| RES-13 | M | `EvidenceNetworkViz.tsx:232,556` | Nodes aren't keyboard-reachable, and the detail panel renders below the fold. | Use `tabIndex` nodes and a right-column inspector. | 5 | done | sprint-5 |
| RES-14 | L | `EvidenceNetworkViz.tsx:216,431` | Arrows on symmetric edges, exported SVG loses its colours, and there's no cluster legend. | Draw arrows only for citations, inline colours on export, and add a legend. | 5 | done | sprint-5 |
| RES-15 | M | `constants.ts:23-40` vs `422-440` | Two label sets for the same phases ("Ext. Quality" vs "Extraction & Quality"). | Keep one `PHASE_LABELS` with a `short` field. | 5 | done | sprint-1 |
| RES-16 | L | multiple | "--" used as a dash in UI copy. | Use "·" or "–". | 5 | done | sprint-5 |
| DAT-01 | H | `database/PapersTable.tsx:34`, `ui/table.tsx:16` | No column sort and no `aria-sort`. | Sortable `Th` with a chevron. | 4 | done | sprint-4 |
| DAT-02 | H | `DatabaseView.tsx:210` | The Papers pagination renders below the *Outcomes* table. | Put the pager inside the Papers shell footer or toolbar. | 4 | done | sprint-4 |
| DAT-03 | H | `DatabaseView.tsx:197` | "No papers found." appears even when filters caused it, with no way out. | Show "No papers match 3 filters" with Clear filters. | 4 | done | sprint-4 |
| DAT-04 | H | `hooks/useDbFilters.ts:89` | Filters and page are lost on tab switch or reload, and views can't be linked. | Sync them to URL search params. | 4 | done | sprint-4 |
| DAT-05 | H | `DatabaseFiltersPopover.tsx`, `FilterComboboxPopover.tsx` | Filters are two popovers deep, single-value, with no counts. | Inline facets with counts, multi-select and a year range. | 4 | done | sprint-4 |
| DAT-06 | M | `FilterComboboxPopover.tsx:58` | Typing "incl" filters the table before a value is picked. | Apply on select for categorical fields. | 4 | done | sprint-4 |
| DAT-07 | M | `PapersTable.tsx:31-43` | 10 columns, no sticky header or first column, and no column toggle. | Sticky header, Columns menu, and merge TA/FT/Status into one "Screening" cell. | 4 | done | sprint-4 |
| DAT-08 | M | `PapersTable.tsx:56-86` | Truncated with no title attribute and no row detail. | Open a side drawer with the abstract, reasons, DOI and extraction. | 4 | done | sprint-4 |
| DAT-09 | M | `PapersTable.tsx:98-166` | Two badge shapes in one row and raw snake_case. | Use `Badge` with humanised labels. | 4 | done | sprint-4 |
| DAT-10 | M | `PapersTable.tsx:30` | Double frame (data-surface inside glass-table-shell) with mismatched radii. | Use one frame. | 4 | done | sprint-4 |
| DAT-11 | M | `OutcomesTable.tsx:71-90` | Silent 200-row cap, left-aligned numbers, no tabular numerals. | Right-align with tabular-nums, format `p<0.001`, paginate. | 4 | done | sprint-4 |
| DAT-12 | M | `DatabaseView.tsx` | No CSV/RIS export, a core systematic-review deliverable. | Add an Export button that respects the current filters. | 4 | done | sprint-4 |
| DAT-13 | L | `DatabaseView.tsx:126,186` | "Complete" is bare green text. | Use Badge. | 4 | done | sprint-4 |
| DAT-14 | L | `ui/table.tsx:108` | The pager hides itself at 1 page and has no page-size control. | Always show the count, and add a 50/100/250 select. | 4 | done | sprint-4 |
| DAT-15 | L | `FilterChipBar.tsx:31` | 12px remove targets. | Make them at least 24px. | 4 | done | sprint-4 |
| CST-02 | H | `CostView.tsx:258-265` | A rainbow of phase colours on a labelled bar chart, plus redundant axis, labels and tooltip. The top bar is grey. | One hue, direct labels "$0.41 · 34%", and no X axis. | 4 | done | sprint-4 |
| CST-03 | H | `CostView.tsx:139` vs `285` | The chart sorts descending but the table uses raw order. | Share one sort, and add % and a total row to the table. | 4 | done | sprint-4 |
| CST-04 | H | `CostView.tsx:194-221` | Raw totals only. | Add "$0.20 / included study · $0.70 / 1k screened" and compact numbers (12.3M). | 4 | done | sprint-4 |
| CST-05 | M | `CostView.tsx:61` | Large numbers overflow tiles. | `min-w-0 truncate` plus compact format. | 4 | done | sprint-4 |
| CST-06 | M | `CostView.tsx:303,348` | Spend is shown in success green. | Use neutral colour, and reserve colour for over-budget. | 4 | done | sprint-4 |
| CST-07 | M | `CostView.tsx:197` vs `costOpsFormatters.ts:43` | Two currency formatters, so tooltip and table disagree. | Use `formatUsd` everywhere. | 4 | done | sprint-4 |
| CST-08 | M | `CostView.tsx:339` | The provider is stripped, so rows are ambiguous. | Show the provider as muted secondary text. | 4 | done | sprint-4 |
| CST-09 | M | `CostView.tsx:151,359` | Export only exists behind `?ops=1`, and the label shows literal backticks. | Always offer a per-run export. | 4 | done | sprint-4 |
| CST-10 | M | `CostOpsChartSection.tsx:90,228` | 9px ticks at -38° cut to 4-letter stems. | Horizontal bars with full labels and an 11px minimum. | 4 | done | sprint-4 |
| CST-11 | M | `CostOpsChartSection.tsx:70,151,244` | Silent slices at 8, 12 and 24. | Add an "Other" bucket and "showing last 24". | 4 | done | sprint-4 |
| CST-12 | M | `costOpsFormatters.ts:248` | `text-primary-foreground` doesn't exist, which gives 3.23:1 contrast in light mode. | Use `text-intent-primary-fg`. | 4 | done | sprint-4 |
| CST-13 | L | `costOpsFormatters.ts:240` | 3-column grid holding 2 items. | `md:grid-cols-2`. | 4 | done | sprint-4 |
| CST-14 | L | `CostOpsToolbar.tsx:27` vs `ChartTableToggle.tsx` | The segmented control is duplicated. | Reuse one, with `role=group`. | 4 | done | sprint-4 |
| CST-15 | L | `CostView.tsx:444-491` | Validation diagnostics live on the Cost tab, with colour-only status and a silent cap at 8. | Move them to Quality, use Badges and "show all". | 4 | done | sprint-4 |
| CST-16 | L | `CostView.tsx:180,191` | Wrong empty copy for finished runs, and `max-w-4xl` leaves wide screens empty. | Choose copy by state and widen. | 4 | done | sprint-4 |
| DS-01 | H | `ui/button.tsx:8` | **`focus-visible:outline-none` kills the focus ring on every Button** (verified in the compiled CSS). The fallback ring is 1.8–2.0:1. | `focus-visible:ring-2 ring-ring ring-offset-2`, at full opacity. | 1 | done | sprint-1 |
| DS-02 | H | `tokens.css:52-65`, `theme-overrides.css:44-57` | Solid buttons fail contrast in dark mode: success 1.84, warning 1.61, danger 2.53, primary 3.86. | Add `--color-intent-*-solid` fill tokens (#7c3aed, #047857, #b45309, #b91c1c) or dark text on light fills. | 1 | done | sprint-1 |
| DS-03 | H | `tokens.css:25` | `--color-muted #71717a` gives 3.67:1 on surface-1, and it's the most-used secondary text colour at 10–11px. | Raise it to about #8b8b94 or lighter in dark mode. | 1 | done | sprint-1 |
| DS-04 | M | `theme-overrides.css:220-251` | Light badges: warning 2.86, success 3.32, danger 3.95. | Darker `--color-intent-*-text` for light mode. | 1 | done | sprint-1 |
| DS-05 | M | `components.css:12-74,351` | `glass-panel-strong` mixes in black even in light mode, so popovers look muddy grey. | Override the `background` shorthand, or mix with white. | 1 | done | sprint-1 |
| DS-06 | M | `tokens.css:179-191`, `base.css:42-87` | A dead, invalid ambient-gradient token, plus hard-coded rgb values in base. | Keep one source. | 1 | done | sprint-1 |
| DS-07 | M | `base.css:4-73` | A parallel legacy HSL token system drives borders and body colour. | Point base rules at the `--color-*` tokens and delete the aliases. | 1 | done | sprint-1 |
| DS-08 | M | 46 sites | `text-[10px]` / `text-[11px]` drift, and the `--text-micro` token is unused. | Add a `--text-2xs` (11px) floor and a 1.2 scale, and lint for arbitrary sizes. | 1 | done | sprint-1 |
| DS-09 | M | `button.tsx:27` plus 13 call sites | Heights h-5 through h-11 set via overrides. | Add `xs` and `icon-sm` sizes to cva and ban overrides. Default to h-9 given the density setting of 8. | 1 | done | sprint-1 |
| DS-10 | M | TSX (157 sites) | Five radius values are used ad hoc. | Map panel, control and pill to `@theme --radius-*`. | 1 | done | sprint-1 |
| DS-11 | M | `CostView.tsx:56`, `costOpsFormatters.ts:237`, `components.css:5-159` | Three stat-tile styles, copied card classes, and raw date inputs. | Build one `StatTile` primitive, alias the card classes, use `DateInput`. | 1 | done | sprint-1 |
| DS-12 | L | `base.css:90`, `components.css:441` | Two reduced-motion blocks, and spinners freeze. | Keep one block and give spinners a slow pulse. | 1 | done | sprint-1 |
| DS-13 | L | `theme-overrides.css:2-155` | All dark values duplicated, and some duplicate hues (community 0/6, phases 4/4b). | Keep a single source and use distinct hues. | 1 | done | sprint-1 |
| DS-14 | L | `feedback.tsx:72`, `tokens.css:22` | The empty-state icon is 1.3:1, and borders are 1.2–1.3:1. | Add `--color-border-strong` of at least 1.6:1. | 1 | done | sprint-1 |
| DS-15 | L | `ui/section.tsx:68-180` | Collapsible sections lack aria-expanded, and `!h-auto` hacks are used. | Add ARIA and an auto-height toolbar variant. | 1 | done | sprint-1 |

## Sprint logs

_(append per sprint: landed, blocked, next)_

### Sprint 1: Foundation (2026-09-28)
**Landed**
- **DS-01..15:** tokens (solid/text/border-strong/ring/scrim/2xs/radius), a single dark source, a Button focus ring and size scale, Badge contrast, and the StatTile, DropdownMenu, RadioGroup and Sheet primitives. The 46 arbitrary font sizes, 18 Button height overrides and about 43 radius usages were swept, and ESLint guardrails were added.
- **ACT-10, RES-15:** `PHASE_META` is the single label source, `lib/humanize.ts` was added, the header status fallback was fixed, and labels are now sentence case.

**Decisions**
- The Retry button stays at h-7.
- A scrim token was added.
- Labels use sentence case.
- `phasesInMilestone` dedupes aliases.
- Status wins over the `is*` flags.

**Follow-ups for later sprints**
- Two phases both render as short label "Extraction" in the cost chart: `phase_4_extraction_quality` and `phase_4_extraction` (CST sprint).
- Migrate consumers to `phaseLabel`, `shortModelName`, `humanizeStage` and `decodeHtmlEntities`. The file:line list is in the WS-C report, and the targets include logLine.ts, CostView.tsx, ScreeningPaperRow.tsx, PapersTable.tsx and EvidenceNetworkViz.tsx.
- The SVG font sizes in EvidenceNetworkViz stay at 9/10px (RES sprint).

**Next:** Sprint 2 (Status and safety). BE-01..03 is already in progress in a worktree.

### Sprint 2: Status and safety (2026-09-28)

**Landed**
- **ACT-01..13:**
  - stepper sub-status, also shown live in the chrome
  - explicit "Resume from…" with a confirm dialog listing phases and prior spend
  - failure banner with actions
  - "Waiting on you" banner, including config_generating
  - auto-routing to the action tab (deep links respected)
  - underline tabs with the gate tab second
  - outcome-first strip and Funnel popover
  - mobile: stepper shows only the current label, and the download button is hidden
  - `warn` event rendering
- **SHL-01..17:**
  - overlay-link cards
  - Radix actions menu and undo toasts
  - named delete dialog and inline confirm errors
  - completed runs default into the Completed lane, with a localStorage pin for "Move to In progress"
  - "In progress" naming
  - collapsed lane icons
  - Sheet mobile drawer
  - keyboard resize
  - Cmd+B guard

**Decisions**
- Gate banners are violet (primary).
- Resume confirm uses the primary style and wording "Previously spent on these phases".
- `needs_revision` stays In progress.
- Uncertain papers are kept in extraction (backend behaviour, stated in the screening confirm).
- Methods wording is "automated reviewers" (user decision).

**Open follow-ups**
- Gate banner decision count: wire it after Sprint 3 merges.
- A sidebar re-click on an awaiting_review run should re-route to the gate tab (`useRunLifecycleActions`).
- Archiving the viewed run navigates home; Undo should return to it.
- Persist the "moved to In progress" pin in the backend (currently per-browser).
- Delete leaves empty parent `wf-*` folders.

**In flight**
- BE-01..03 and the screening backend fixes (return AI excludes, fix the approval cohort data loss, idempotent overrides, thresholds) in the backend worktree.
- Sprint 3 frontend done (branch 734ef4f), awaiting merge.
### Sprint 3: Screening gate (2026-09-28)

**Landed (SCR-01..10)**
- Triage list with inline Include/Exclude toggles.
- Keyboard: j/k to move, i/e to include or exclude, u for multi-level undo, x to select, ? for help.
- Bulk actions.
- Filters: All/Include/Exclude/Uncertain/Overridden, with search and sort by confidence ascending.
- Full abstract, reason seeded from the saved override, and "Decided by" / exclusion reason on each paper.
- Header shows live counts and explains the thresholds.
- Sticky primary approval bar with a summary confirm. It states that Uncertain papers are kept in extraction.
- Approve and resume errors are split.
- 200-row paging.
- The gate banner shows the pending decision count.
- Backend (fbf8640): the summary returns AI excludes and final decisions, the cohort data-loss bug is fixed, and override writes are idempotent.

**Not visually verified:** no run is currently awaiting review. Check on the next live gate.
### Sprint 4: Data and Cost (2026-09-28)

**Landed**
- **DAT-01..15**
  - Server-side sort (whitelisted), multi-value facets with counts, a year range, and CSV/RIS export (formula-escaped).
  - A paper detail endpoint feeding a Sheet inspector.
  - URL-synced filter state.
  - Merged Screening cell, Columns toggle with empty columns auto-hidden, sticky header and title column.
  - Pager in the table footer.
  - Filtered empty state.
  - Outcomes numerics.
- **CST-01..16**
  - Single-hue direct-labelled bars showing share %, with alias phases merged.
  - Chart and table share one sort; the table has a total row.
  - StatTiles with per-included-study and per-1k-records cost.
  - One `formatUsd` everywhere.
  - Per-run CSV export.
  - Ops charts with an Other bucket.
  - `ValidationDiagnostics` extracted, to be mounted in Quality in Sprint 5.

**Follow-ups**
- Source values show raw ("semantic_scholar"), so humanize the source names.
- The cost tile subline truncates on narrow tiles.
- Outcomes table is not filter-aware yet (needs a filter-aware /tables endpoint).
- Year sort starts ascending.
- Column visibility isn't persisted.
### Sprint 5: Results (2026-09-28)

**Landed (RES-01..14, 16)**
- **Manuscript view:** 68ch column with page scroll, a sticky toolbar, an outline rail with scroll-spy, and a "Draft quality" chip that flags template text. Print is fixed and tables scroll horizontally.
- **Figures and diagrams:** missing figures show a placeholder, and custom diagrams show real counts with download.
- **Quality tab:** audit findings come from /manuscript-audit, with a segmented, collapsible summary that `needs_revision` runs and the chrome button deep-link to. `ValidationDiagnostics` is mounted here.
- **Submission package:** one state machine drives build, rebuild (with confirmation) and download.
- **Gate:** the locked state is gate-aware ("Waiting on your screening review") and shows "Files so far".
- **References:** search, a "Full text only" filter, and ARIA fixes.
- **Evidence network:** nodes are reachable by keyboard, there is an inspector column and a legend, arrows appear only on citations, and export uses inlined colours.

**Follow-ups**
- Humanize source names (openalex_content, semantic_scholar) in References and Data.
- Warn on package build when the draft-quality check flags template text.
- Evidence network SVG export should always use light-theme colours.
### Sprint 6: Setup, shell, log (2026-09-28)

**Landed**
- **SET-01..16**
  - Setup page: h1, research question first, review-type cards with "Help me decide", a quiz with a step counter and Back.
  - Up-front API key check, with a link that opens Settings on the Keys tab.
  - Accessible CSV drop zone.
  - Reuse-config picker.
  - Pasted YAML can now launch.
  - YAML editor: dirty state, reset and inline validation (new dependency: `yaml`).
  - Config stepper uses real provenance only, with PCC labels for scoping reviews.
  - CRD format hint.
- **SHL-18..28**
  - Copy-question button, a user-facing offline banner, and error-boundary actions.
  - Toasts moved to bottom-right.
  - Settings uses GlassTabs with a width per tab.
  - API keys: required providers listed first, format hints, Clear and a Saved state.
  - CostsPanel extracted and the dead dialog removed.
- **LOG-01..09**
  - Measured virtualisation (new dependency: `@tanstack/react-virtual`) and a sticky phase header.
  - "N new events" pill.
  - Severity chips.
  - Only milestones are announced to screen readers.
  - 12px text floor and readable tags.
  - Short model names, with details behind a chevron expand.
  - Decoded titles.
  - Muted status lines.
  - Search empty state.
  - Narrow-width stacking.

**Decision (user):** PROSPERO registration stays mandatory for every run, scoping reviews included. The skip button stays hidden behind `PROSPERO_SKIP_SUPPORTED = false`, and the copy says registration is required.

**Follow-ups**
- `FetchError` still labels its dismiss action "Retry" app-wide.
- A settings context would let other views open Settings → Keys without rendering their own dialog.
- Decide on an "AI reviewer" method chip for screening-decision log rows.
- The top bar says "New Review" and the h1 says "New review", so the heading is duplicated.
- Key-prefix hints and the "where each key is used" copy are hard-coded.
