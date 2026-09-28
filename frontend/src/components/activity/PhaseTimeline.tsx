import { useEffect, useState } from "react"
import { PHASE_MILESTONES } from "@/lib/constants"
import {
  activeSubStatus,
  buildMilestoneState,
  formatSubStatus,
  type PhaseState,
} from "@/lib/activityPhaseState"
import {
  HorizontalStepper,
  type StepperStep,
  type StepperStepStatus,
} from "@/components/ui/HorizontalStepper"

function mapPhaseStatus(state: PhaseState, awaitingGate: boolean): StepperStepStatus {
  if (state.status === "error") return "error"
  if (awaitingGate || state.status === "awaiting") return "awaiting"
  switch (state.status) {
    case "done":
      return "done"
    case "running":
      return "active"
    default:
      return "pending"
  }
}

const AWAITING_SR: Record<string, string> = {
  prospero: "awaiting PROSPERO registration",
  discovery: "awaiting your review",
}

function useNow(enabled: boolean, intervalMs = 15_000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!enabled) return
    const tick = () => setNow(Date.now())
    const first = setTimeout(tick, 0)
    const timer = setInterval(tick, intervalMs)
    return () => {
      clearTimeout(first)
      clearInterval(timer)
    }
  }, [enabled, intervalMs])
  return now
}

export interface PhaseTimelineProps {
  phaseStates: Record<string, PhaseState>
  loading: boolean
  completedWorkflow: boolean
  /** Show the live sub-status line (sub-phase, progress, elapsed) under the active step. */
  showSubStatus?: boolean
  awaitingGateByMilestone?: Partial<Record<string, boolean>>
}

export function PhaseTimeline({
  phaseStates,
  loading,
  completedWorkflow,
  showSubStatus = false,
  awaitingGateByMilestone,
}: PhaseTimelineProps) {
  const now = useNow(showSubStatus)
  const sub = showSubStatus ? activeSubStatus(phaseStates, now) : null

  const steps: StepperStep[] = PHASE_MILESTONES.map((milestone) => {
    const isAwaitingGate = Boolean(awaitingGateByMilestone?.[milestone.key])
    const state = buildMilestoneState(milestone.phases, phaseStates, completedWorkflow)
    const status = mapPhaseStatus(state, isAwaitingGate)
    const showHere =
      sub !== null && sub.milestone === milestone.key && (status === "active" || status === "awaiting")
    return {
      key: milestone.key,
      label: milestone.label,
      status,
      subStatus: showHere ? formatSubStatus(sub) : null,
      srStatus: status === "awaiting" ? (AWAITING_SR[milestone.key] ?? "waiting on you") : undefined,
    }
  })

  return (
    <HorizontalStepper
      steps={steps}
      loading={loading}
      loadingStepCount={PHASE_MILESTONES.length}
      aria-label="Run progress"
    />
  )
}
