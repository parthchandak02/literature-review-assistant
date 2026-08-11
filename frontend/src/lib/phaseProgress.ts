// Shared phase progress computation for sidebar and activity views.
// Derives overall progress (0-1) from SSE events.

import { PHASE_ORDER } from "@/lib/constants"
import type { ReviewEvent } from "@/lib/api"

export const PROSPERO_GATE_PHASE = "phase_1_prospero_gate"
export const HUMAN_REVIEW_PHASE = "human_review_checkpoint"

/** True when the run is parked at or actively in the PROSPERO registration gate. */
export function detectAwaitingProspero(input: {
  historicalStatus?: string | null
  status?: string
  events?: ReviewEvent[]
  isRunning?: boolean
  prosperoPrepareInProgress?: boolean
}): boolean {
  const {
    historicalStatus,
    status = "",
    events = [],
    isRunning = false,
    prosperoPrepareInProgress = false,
  } = input
  if (
    historicalStatus === "awaiting_prospero" ||
    status === "awaiting_prospero" ||
    prosperoPrepareInProgress
  ) {
    return true
  }

  const parkedFromEvents = events.some((e) => {
    if (e.type === "done") {
      return String(e.outputs?.status ?? "").toLowerCase() === "awaiting_prospero"
    }
    if (e.type === "phase_done" && e.phase === PROSPERO_GATE_PHASE) {
      const summary = e.summary as Record<string, unknown> | undefined
      return Boolean(summary?.awaiting_prospero || summary?.paused)
    }
    return false
  })
  if (parkedFromEvents) return true

  if (!isRunning) return false
  return (
    events.some((e) => e.type === "phase_start" && e.phase === PROSPERO_GATE_PHASE) &&
    !events.some((e) => e.type === "phase_done" && e.phase === PROSPERO_GATE_PHASE)
  )
}

/** True when the run is parked at or actively in the human screening review gate. */
export function detectAwaitingReview(input: {
  historicalStatus?: string | null
  status?: string
  events?: ReviewEvent[]
  isRunning?: boolean
}): boolean {
  const { historicalStatus, status = "", events = [], isRunning = false } = input
  if (historicalStatus === "awaiting_review" || status === "awaiting_review") {
    return true
  }
  if (!isRunning) return false
  return (
    events.some((e) => e.type === "phase_start" && e.phase === HUMAN_REVIEW_PHASE) &&
    !events.some((e) => e.type === "phase_done" && e.phase === HUMAN_REVIEW_PHASE)
  )
}

export interface PhaseProgress {
  /** Fraction of total phases completed (0-1). */
  value: number
  /** Number of phases fully done. */
  completedPhases: number
  /** Current phase progress fraction if running (0-1). */
  currentPhaseFraction?: number
}

function buildPhaseStates(events: ReviewEvent[]): Record<string, { status: string; progress?: { current: number; total: number } }> {
  const states: Record<string, { status: string; progress?: { current: number; total: number } }> = {}
  for (const ev of events) {
    if (ev.type === "phase_start") {
      states[ev.phase] = { status: "running" }
    } else if (ev.type === "phase_done") {
      states[ev.phase] = {
        status: "done",
        progress:
          ev.total != null && ev.completed != null
            ? { current: ev.completed, total: ev.total }
            : undefined,
      }
    } else if (ev.type === "progress") {
      // Progress can arrive without an in-memory phase_start marker after event capping/replay.
      // Initialize the phase as running so progress bars do not appear frozen.
      const prev = states[ev.phase]
      states[ev.phase] = {
        status: prev?.status ?? "running",
        progress: { current: ev.current, total: ev.total },
      }
    }
  }
  // When run is complete, infer "done" for phases with start but no done (event truncation).
  const hasTerminal =
    events.some(
      (e) => e.type === "done" || e.type === "error" || e.type === "cancelled",
    ) || Boolean(states.finalize?.status === "done")
  if (hasTerminal) {
    for (const phase of PHASE_ORDER) {
      const s = states[phase]
      if (s?.status === "running") {
        states[phase] = { ...s, status: "done" }
      }
    }
  }
  return states
}

/**
 * Compute overall phase progress from SSE events.
 * Returns value in [0, 1] where 1 = all 6 phases done.
 */
export function computePhaseProgress(events: ReviewEvent[]): PhaseProgress {
  const states = buildPhaseStates(events)
  const totalPhases = PHASE_ORDER.length

  let completedPhases = 0
  let currentPhaseFraction: number | undefined

  for (const phase of PHASE_ORDER) {
    const state = states[phase]
    if (!state) {
      // Older runs may omit optional protocol phases (for example PROSPERO gate).
      continue
    }
    if (state.status === "done") {
      completedPhases += 1
    } else if (state.status === "running" && state.progress && state.progress.total > 0) {
      currentPhaseFraction = state.progress.current / state.progress.total
      break
    } else {
      break
    }
  }

  const value =
    currentPhaseFraction != null
      ? (completedPhases + currentPhaseFraction) / totalPhases
      : completedPhases / totalPhases

  return {
    value: Math.min(1, value),
    completedPhases,
    currentPhaseFraction,
  }
}
