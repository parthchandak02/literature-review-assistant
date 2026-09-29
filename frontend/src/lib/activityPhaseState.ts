import {
  PHASE_META,
  PHASE_MILESTONES,
  PHASE_ORDER,
  RESUME_PHASE_ORDER,
  phaseLabel,
  phaseTitle,
  resolvePhaseId,
  type MilestoneId,
} from "@/lib/constants"
import { PROSPERO_GATE_PHASE } from "@/lib/phaseProgress"
import type { ReviewEvent } from "@/lib/api"

export type PhaseStatus = "pending" | "running" | "done" | "error" | "awaiting"

export type GateStatus = "awaiting_prospero" | "awaiting_review"

export interface PhaseState {
  status: PhaseStatus
  gateStatus?: GateStatus
  progress?: { current: number; total: number }
  startedTs?: string
  doneTss?: string
}

const DISCOVERY_GATE_PHASES = new Set(
  PHASE_MILESTONES.find((milestone) => milestone.key === "discovery")?.phases ?? [
    "phase_2_search",
    "phase_3_screening",
    "fulltext_pdf_retrieval",
  ],
)

export function applyGateOverrides(
  phaseStates: Record<string, PhaseState>,
  gates: { awaitingProspero: boolean; awaitingReview: boolean },
): Record<string, PhaseState> {
  const next = { ...phaseStates }

  if (gates.awaitingProspero) {
    const prosperoState = next[PROSPERO_GATE_PHASE]
    next[PROSPERO_GATE_PHASE] = {
      ...prosperoState,
      status: "awaiting",
      gateStatus: "awaiting_prospero",
      startedTs: prosperoState?.startedTs,
      doneTss: prosperoState?.doneTss,
      progress: prosperoState?.progress,
    }
  }

  if (gates.awaitingReview) {
    const reviewPhase =
      [...DISCOVERY_GATE_PHASES].reverse().find((phase) => {
        const phaseState = next[phase]
        return phaseState?.status === "running" || phaseState?.status === "done"
      }) ?? "phase_3_screening"
    const reviewState = next[reviewPhase]
    next[reviewPhase] = {
      ...reviewState,
      status: "awaiting",
      gateStatus: "awaiting_review",
      startedTs: reviewState?.startedTs,
      doneTss: reviewState?.doneTss,
      progress: reviewState?.progress,
    }
  }

  return next
}

export function buildPhaseStates(events: ReviewEvent[], workflowCompleted: boolean): Record<string, PhaseState> {
  const states: Record<string, PhaseState> = {}
  for (const ev of events) {
    if (ev.type === "phase_start") {
      states[ev.phase] = { status: "running", startedTs: ev.ts }
    } else if (ev.type === "phase_done") {
      states[ev.phase] = {
        status: "done",
        startedTs: states[ev.phase]?.startedTs,
        doneTss: ev.ts,
        progress:
          ev.total != null && ev.completed != null
            ? { current: ev.completed, total: ev.total }
            : undefined,
      }
    } else if (ev.type === "progress") {
      const prev = states[ev.phase]
      states[ev.phase] = {
        status: prev?.status ?? "running",
        startedTs: prev?.startedTs,
        doneTss: prev?.doneTss,
        progress: { current: ev.current, total: ev.total },
      }
    }
  }
  if (workflowCompleted) {
    for (const phase of PHASE_ORDER) {
      const s = states[phase]
      if (s?.status === "running") {
        states[phase] = { ...s, status: "done", doneTss: s.doneTss ?? s.startedTs }
      }
    }
  }
  return states
}

export function isPhaseEligibleForResume(
  phase: string,
  phaseStates: Record<string, PhaseState>,
  completedWorkflow: boolean,
): boolean {
  if (!RESUME_PHASE_ORDER.includes(phase as (typeof RESUME_PHASE_ORDER)[number])) return false
  const idx = RESUME_PHASE_ORDER.indexOf(phase as (typeof RESUME_PHASE_ORDER)[number])
  if (idx < 0) return false
  if (completedWorkflow) {
    return phaseStates[phase]?.status === "done"
  }
  for (let i = 0; i < idx; i++) {
    const prereq = RESUME_PHASE_ORDER[i]
    if (phaseStates[prereq]?.status !== "done") return false
  }
  const state = phaseStates[phase]
  return Boolean(state && (state.status === "done" || state.status === "running" || state.status === "error"))
}

export function isPhaseResumeSelectable(
  phase: string,
  phaseStates: Record<string, PhaseState>,
  completedWorkflow: boolean,
): boolean {
  return isPhaseEligibleForResume(phase, phaseStates, completedWorkflow)
}

export function buildMilestoneState(
  phases: readonly string[],
  phaseStates: Record<string, PhaseState>,
  completedWorkflow: boolean,
): PhaseState {
  const states = phases.map((phase) => phaseStates[phase] ?? { status: "pending" as const })
  if (states.some((s) => s.status === "error")) {
    return { status: "error" }
  }
  const awaitingState = states.find((s) => s.status === "awaiting")
  if (awaitingState) {
    return {
      status: "awaiting",
      gateStatus: awaitingState.gateStatus,
      progress: awaitingState.progress,
      startedTs: awaitingState.startedTs,
      doneTss: awaitingState.doneTss,
    }
  }
  const allDone = states.every((s) => s.status === "done")
  if (allDone) {
    const firstStarted = states.find((s) => s.startedTs)?.startedTs
    const lastDone = [...states].reverse().find((s) => s.doneTss)?.doneTss
    return { status: "done", startedTs: firstStarted, doneTss: lastDone }
  }
  if (completedWorkflow) {
    const completedState = states.find((s) => s.status === "done" || s.status === "running")
    if (completedState) {
      return {
        status: "done",
        progress: completedState.progress,
        startedTs: completedState.startedTs,
        doneTss: completedState.doneTss ?? completedState.startedTs,
      }
    }
    return { status: "pending" }
  }
  const runningState = states.find((s) => s.status === "running" || s.status === "done")
  if (runningState) {
    return {
      status: "running",
      progress: runningState.progress,
      startedTs: runningState.startedTs,
      doneTss: runningState.doneTss,
    }
  }
  return { status: "pending" }
}

type TimelinePhase = (typeof PHASE_ORDER)[number]
type ResumePhase = (typeof RESUME_PHASE_ORDER)[number]

function parseTs(raw: string): number {
  const iso = raw.includes("T") ? raw : `${raw.replace(" ", "T")}Z`
  return new Date(iso).getTime()
}

/** Compact elapsed time: "45s", "6m", "1h 12m". */
export function formatElapsed(ms: number): string {
  const secs = Math.max(0, Math.floor(ms / 1000))
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m`
  const hours = Math.floor(mins / 60)
  const rest = mins % 60
  return rest ? `${hours}h ${rest}m` : `${hours}h`
}

/**
 * The phase the run is on: an awaiting gate first, otherwise the running phase
 * that started most recently (so a sub-phase wins over its parent).
 */
export function currentPhaseId(phaseStates: Record<string, PhaseState>): string | null {
  const entries = Object.entries(phaseStates)
  const awaiting = entries.find(([, state]) => state.status === "awaiting")
  if (awaiting) return awaiting[0]
  let best: { phase: string; ts: number } | null = null
  for (const [phase, state] of entries) {
    if (state.status !== "running") continue
    const parsed = state.startedTs ? parseTs(state.startedTs) : Number.NaN
    const ts = Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY
    if (!best || ts >= best.ts) best = { phase, ts }
  }
  return best?.phase ?? null
}

export interface ActiveSubStatus {
  phase: string
  milestone: MilestoneId | null
  label: string
  progressText: string | null
  elapsedText: string | null
  awaiting: boolean
}

function formatCount(value: number): string {
  return value.toLocaleString("en-US")
}

/** Sub-status of the active step, e.g. label "PDF retrieval", progressText "34/120", elapsedText "6m". */
export function activeSubStatus(
  phaseStates: Record<string, PhaseState>,
  now: number | Date,
): ActiveSubStatus | null {
  const phase = currentPhaseId(phaseStates)
  if (!phase) return null
  const state = phaseStates[phase]
  const awaiting = state.status === "awaiting"
  const progress = state.progress
  const progressText =
    progress && progress.total > 0
      ? `${formatCount(Math.min(progress.current, progress.total))}/${formatCount(progress.total)}`
      : null
  let elapsedText: string | null = null
  if (!awaiting && state.startedTs) {
    const started = parseTs(state.startedTs)
    const nowMs = typeof now === "number" ? now : now.getTime()
    if (Number.isFinite(started)) elapsedText = formatElapsed(nowMs - started)
  }
  const id = resolvePhaseId(phase)
  return {
    phase,
    milestone: id ? PHASE_META[id].milestone : null,
    label: phaseLabel(phase, "short"),
    progressText,
    elapsedText,
    awaiting,
  }
}

/** "PDF retrieval · 34/120 · 6m" */
export function formatSubStatus(sub: ActiveSubStatus): string {
  return [sub.label, sub.progressText, sub.elapsedText].filter(Boolean).join(" · ")
}

const NON_NUMBERED_PARENT: Record<string, TimelinePhase> = {
  screening_calibration: "phase_3_screening",
  screening_batch_ranker: "phase_3_screening",
  criteria_refinement: "phase_3_screening",
  human_review_checkpoint: "phase_3_screening",
  citation_chasing: "phase_3_screening",
  quality_rob2: "phase_4_extraction_quality",
  quality_robins_i: "phase_4_extraction_quality",
  quality_casp: "phase_4_extraction_quality",
  quality_mmat: "phase_4_extraction_quality",
}

/** Map a phase, sub-phase or cost-record key to its PHASE_ORDER phase. */
export function timelinePhaseFor(raw: string): TimelinePhase | null {
  const id: string = resolvePhaseId(raw) ?? raw
  if ((PHASE_ORDER as readonly string[]).includes(id)) return id as TimelinePhase
  if (NON_NUMBERED_PARENT[id]) return NON_NUMBERED_PARENT[id]
  const match = /^phase_(\d+)([a-z]?)/.exec(id)
  if (!match) return null
  const [, num, letter] = match
  const exact = letter ? PHASE_ORDER.find((p) => p.startsWith(`phase_${num}${letter}_`)) : undefined
  return exact ?? PHASE_ORDER.find((p) => p.startsWith(`phase_${num}_`)) ?? null
}

/** Timeline phases that run again when resuming from `phase`. */
export function phasesRerunFrom(phase: string): TimelinePhase[] {
  const idx = PHASE_ORDER.indexOf(phase as TimelinePhase)
  return idx < 0 ? [] : PHASE_ORDER.slice(idx)
}

/** Prior spend of the given timeline phases; null when there is no cost data. */
export function priorCostForPhases(
  byPhase: ReadonlyArray<{ phase: string; cost_usd: number }> | null | undefined,
  phases: readonly string[],
): number | null {
  if (!byPhase || byPhase.length === 0) return null
  const wanted = new Set(phases)
  let total = 0
  for (const row of byPhase) {
    const parent = timelinePhaseFor(row.phase)
    if (parent && wanted.has(parent)) total += row.cost_usd || 0
  }
  return total
}

export interface ResumeOption {
  phase: ResumePhase
  label: string
  title?: string
  selectable: boolean
}

export function resumeOptions(
  phaseStates: Record<string, PhaseState>,
  completedWorkflow: boolean,
): ResumeOption[] {
  return RESUME_PHASE_ORDER.map((phase) => ({
    phase,
    label: phaseLabel(phase, "long"),
    title: phaseTitle(phase),
    selectable: isPhaseResumeSelectable(phase, phaseStates, completedWorkflow),
  }))
}

/** Latest resumable phase; the failure banner offers to resume from it. */
export function latestResumablePhase(
  phaseStates: Record<string, PhaseState>,
  completedWorkflow: boolean,
): ResumePhase | null {
  const options = resumeOptions(phaseStates, completedWorkflow)
  for (let i = options.length - 1; i >= 0; i--) {
    if (options[i].selectable) return options[i].phase
  }
  return null
}

/** Mark the phase the run died in, and its timeline parent, as errored. */
export function applyFailure(
  phaseStates: Record<string, PhaseState>,
  failedPhase: string | null,
): Record<string, PhaseState> {
  if (!failedPhase) return phaseStates
  const next = { ...phaseStates }
  for (const phase of new Set([failedPhase, timelinePhaseFor(failedPhase) ?? failedPhase])) {
    const prev = next[phase]
    if (!prev || prev.status !== "running") continue
    next[phase] = { ...prev, status: "error" }
  }
  return next
}

export interface FailureSummary {
  phase: string | null
  message: string
}

/** Last error message, and the phase that was running when the run failed. */
export function failureSummary(
  events: ReviewEvent[],
  phaseStates: Record<string, PhaseState>,
): FailureSummary {
  let message: string | null = null
  for (let i = events.length - 1; i >= 0 && message === null; i--) {
    const ev = events[i]
    if (ev.type === "error" && ev.msg) message = ev.msg
  }
  for (let i = events.length - 1; i >= 0 && message === null; i--) {
    const ev = events[i]
    if (ev.type === "done" && typeof ev.outputs?.error === "string" && ev.outputs.error) {
      message = ev.outputs.error
    }
  }
  return {
    phase: currentPhaseId(phaseStates),
    message: message ?? "An unexpected error occurred.",
  }
}
