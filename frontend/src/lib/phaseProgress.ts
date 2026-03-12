// Shared phase progress computation for sidebar and activity views.
// Derives overall progress (0-1) from SSE events.

import { PHASE_ORDER } from "@/lib/constants"
import type { ReviewEvent } from "@/lib/api"

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
    if (!state) break
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
