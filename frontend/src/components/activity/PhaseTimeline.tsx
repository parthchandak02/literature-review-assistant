import { PHASE_MILESTONES } from "@/lib/constants"
import { buildMilestoneState, type PhaseState } from "@/lib/activityPhaseState"
import {
  HorizontalStepper,
  type StepperStep,
  type StepperStepStatus,
} from "@/components/ui/HorizontalStepper"

function mapPhaseStatus(state: PhaseState, awaitingGate: boolean): StepperStepStatus {
  if (awaitingGate || state.status === "awaiting") return "awaiting"
  switch (state.status) {
    case "done":
      return "done"
    case "running":
      return "active"
    case "error":
      return "error"
    default:
      return "pending"
  }
}

export interface PhaseTimelineProps {
  phaseStates: Record<string, PhaseState>
  loading: boolean
  completedWorkflow: boolean
  canResumeFromTimeline: boolean
  isPhaseResumeSelectable: (phase: string) => boolean
  armedResumePhase: string | null
  armedMilestoneStartIdx: number
  awaitingGateByMilestone?: Partial<Record<string, boolean>>
  onResumeTap: (phase: string) => void
}

export function PhaseTimeline({
  phaseStates,
  loading,
  completedWorkflow,
  canResumeFromTimeline,
  isPhaseResumeSelectable,
  armedResumePhase,
  armedMilestoneStartIdx,
  awaitingGateByMilestone,
  onResumeTap,
}: PhaseTimelineProps) {
  const steps: StepperStep[] = PHASE_MILESTONES.map((milestone, index) => {
    const targetPhase =
      milestone.phases.find((phase) => isPhaseResumeSelectable(phase)) ?? milestone.phases[0]
    const isAwaitingGate = Boolean(awaitingGateByMilestone?.[milestone.key])
    const state = buildMilestoneState(milestone.phases, phaseStates, completedWorkflow)
    const inResumeRange = armedMilestoneStartIdx >= 0 && index >= armedMilestoneStartIdx
    const isResumeSelectable = canResumeFromTimeline && isPhaseResumeSelectable(targetPhase)

    let rangeHighlight: StepperStep["rangeHighlight"]
    if (inResumeRange) {
      if (index === armedMilestoneStartIdx && index === PHASE_MILESTONES.length - 1) {
        rangeHighlight = "single"
      } else if (index === armedMilestoneStartIdx) {
        rangeHighlight = "start"
      } else if (index === PHASE_MILESTONES.length - 1) {
        rangeHighlight = "end"
      } else {
        rangeHighlight = "middle"
      }
    }

    return {
      key: milestone.key,
      label: milestone.label,
      status: mapPhaseStatus(state, isAwaitingGate),
      clickable: isResumeSelectable,
      armed: armedResumePhase === targetPhase,
      rangeHighlight,
      onClick: isResumeSelectable ? () => onResumeTap(targetPhase) : undefined,
    }
  })

  return (
    <HorizontalStepper
      steps={steps}
      loading={loading}
      loadingStepCount={PHASE_MILESTONES.length}
    />
  )
}
