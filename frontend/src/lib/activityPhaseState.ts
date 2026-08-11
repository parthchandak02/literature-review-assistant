import { PHASE_ORDER, RESUME_PHASE_ORDER } from "@/lib/constants"
import type { ReviewEvent } from "@/lib/api"

export type PhaseStatus = "pending" | "running" | "done" | "error"

export interface PhaseState {
  status: PhaseStatus
  progress?: { current: number; total: number }
  startedTs?: string
  doneTss?: string
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
