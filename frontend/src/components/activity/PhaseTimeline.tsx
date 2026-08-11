import {
  CheckCircle,
  Circle,
  XCircle,
} from "lucide-react"
import { Spinner } from "@/components/ui/feedback"
import { Skeleton } from "@/components/ui/skeleton"
import { PHASE_LABELS, PHASE_MILESTONES } from "@/lib/constants"
import { buildMilestoneState, type PhaseState } from "@/lib/activityPhaseState"
import { cn } from "@/lib/utils"

function fmtDuration(ms: number): string {
  const secs = Math.floor(ms / 1000)
  if (secs < 60) return `${secs}s`
  return `${Math.floor(secs / 60)}m ${secs % 60}s`
}

interface PhaseStepProps {
  phase: string
  state: PhaseState
  isLast: boolean
  label?: string
  isResumeSelectable?: boolean
  isArmed?: boolean
  inResumeRange?: boolean
  isRangeStart?: boolean
  isRangeEnd?: boolean
  onResumeTap?: (phase: string) => void
}

function PhaseStep({
  phase,
  state,
  isLast,
  label,
  isResumeSelectable = false,
  isArmed = false,
  inResumeRange = false,
  isRangeStart = false,
  isRangeEnd = false,
  onResumeTap,
}: PhaseStepProps) {
  const stepLabel = label ?? PHASE_LABELS[phase] ?? phase

  const durationStr =
    state.status === "done" && state.startedTs && state.doneTss
      ? fmtDuration(new Date(state.doneTss).getTime() - new Date(state.startedTs).getTime())
      : null

  const subLabel =
    state.status === "running" && state.progress
      ? `${state.progress.current}/${state.progress.total}`
      : state.status === "done" && state.progress
      ? `${state.progress.current}/${state.progress.total}`
      : state.status === "running"
      ? "running..."
      : null

  const circleCls = cn(
    "w-7 h-7 sm:w-8 sm:h-8 rounded-full flex items-center justify-center border shrink-0",
    state.status === "done" && "bg-intent-success-subtle border-intent-success-border text-intent-success",
    state.status === "running" && "bg-intent-active-subtle border-intent-active-border text-intent-active",
    state.status === "error" && "bg-intent-danger-subtle border-intent-danger-border text-intent-danger",
    state.status === "pending" && "bg-card border-border text-muted",
  )

  const connectorCls = cn(
    "h-px shrink-0",
    state.status === "done" ? "bg-intent-success" :
    state.status === "running" ? "bg-intent-active" :
    "bg-border",
  )

  const labelCls = cn(
    "text-[10px] sm:text-[11px] text-center leading-tight font-medium px-0 mt-1.5",
    state.status === "done" && "text-foreground",
    state.status === "running" && "text-intent-active",
    state.status === "error" && "text-intent-danger",
    state.status === "pending" && "text-muted",
  )

  const subLabelCls = cn(
    "text-[9px] sm:text-[10px] font-mono mt-0.5 tabular-nums text-center",
    state.status === "running" ? "text-intent-active" : "text-intent-success",
  )

  return (
    <div className="relative flex flex-1 min-w-0 items-start py-1">
      {inResumeRange && (
        <div
          className={cn(
            "absolute left-0 right-0 top-1 h-14 sm:h-14 bg-intent-warning-subtle",
            isRangeStart && "rounded-l-md",
            isRangeEnd && "rounded-r-md",
          )}
          aria-hidden
        />
      )}
      <div className="flex flex-col items-center w-full shrink-0">
        <button
          type="button"
          onClick={() => {
            if (!isResumeSelectable || !onResumeTap) return
            onResumeTap(phase)
          }}
          disabled={!isResumeSelectable}
          className={cn(
            circleCls,
            "relative transition-colors",
            isResumeSelectable && "cursor-pointer hover:border-intent-warning-border",
            isArmed && "border-intent-warning bg-intent-warning-subtle text-intent-warning",
          )}
          title={isResumeSelectable ? "Tap once to arm resume, tap again to confirm" : undefined}
        >
          {state.status === "done" ? (
            <CheckCircle className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
          ) : state.status === "running" ? (
            <Spinner size="md" />
          ) : state.status === "error" ? (
            <XCircle className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
          ) : (
            <Circle className="h-3 w-3 sm:h-3.5 sm:w-3.5" />
          )}
        </button>
        <span className={labelCls}>{stepLabel}</span>
        {subLabel && <span className={subLabelCls}>{subLabel}</span>}
        {durationStr && (
          <span className="text-[9px] sm:text-[10px] font-mono tabular-nums text-muted mt-0.5 text-center">
            {durationStr}
          </span>
        )}
      </div>
      {!isLast && (
        <div className={cn("relative flex-1 mt-3.5 sm:mt-4", connectorCls)} style={{ minWidth: "0.35rem" }} />
      )}
    </div>
  )
}

function HorizontalStepperContent({
  phaseStates,
  loading,
  completedWorkflow,
  canResumeFromTimeline,
  isPhaseResumeSelectable,
  armedResumePhase,
  armedMilestoneStartIdx,
  onResumeTap,
}: {
  phaseStates: Record<string, PhaseState>
  loading: boolean
  completedWorkflow: boolean
  canResumeFromTimeline: boolean
  isPhaseResumeSelectable: (phase: string) => boolean
  armedResumePhase: string | null
  armedMilestoneStartIdx: number
  onResumeTap: (phase: string) => void
}) {
  if (loading) {
    return (
      <div className="overflow-hidden py-2 sm:py-3 flex items-start gap-1">
        {PHASE_MILESTONES.map((milestone, i) => (
          <div key={milestone.key} className="flex items-start flex-1">
            <div className="flex flex-col items-center gap-1.5 w-full shrink-0">
              <Skeleton className="w-7 h-7 sm:w-8 sm:h-8 rounded-full" />
              <Skeleton className="h-2.5 w-8 sm:w-10" />
            </div>
            {i < PHASE_MILESTONES.length - 1 && <div className="flex-1 mt-3.5 sm:mt-4 h-px bg-border" />}
          </div>
        ))}
      </div>
    )
  }
  return (
    <div className="overflow-hidden py-2 sm:py-3">
      <div className="flex items-start w-full gap-0.5 sm:gap-1">
        {PHASE_MILESTONES.map((milestone, i) => {
          const targetPhase = milestone.phases.find((phase) => isPhaseResumeSelectable(phase)) ?? milestone.phases[0]
          const inResumeRange = armedMilestoneStartIdx >= 0 && i >= armedMilestoneStartIdx
          const isRangeStart = inResumeRange && i === armedMilestoneStartIdx
          const isRangeEnd = inResumeRange && i === PHASE_MILESTONES.length - 1
          return (
            <PhaseStep
              key={milestone.key}
              phase={targetPhase}
              label={milestone.label}
              state={buildMilestoneState(milestone.phases, phaseStates, completedWorkflow)}
              isLast={i === PHASE_MILESTONES.length - 1}
              isResumeSelectable={canResumeFromTimeline && isPhaseResumeSelectable(targetPhase)}
              isArmed={armedResumePhase === targetPhase}
              inResumeRange={inResumeRange}
              isRangeStart={isRangeStart}
              isRangeEnd={isRangeEnd}
              onResumeTap={onResumeTap}
            />
          )
        })}
      </div>
    </div>
  )
}

export interface PhaseTimelineProps {
  phaseStates: Record<string, PhaseState>
  loading: boolean
  completedWorkflow: boolean
  canResumeFromTimeline: boolean
  isPhaseResumeSelectable: (phase: string) => boolean
  armedResumePhase: string | null
  armedMilestoneStartIdx: number
  onResumeTap: (phase: string) => void
  resumeModeActive: boolean
  resumeHint: string | null
  canResumeEligibility: boolean
  resumeBlockedReason: string | null
}

export function PhaseTimeline({
  phaseStates,
  loading,
  completedWorkflow,
  canResumeFromTimeline,
  isPhaseResumeSelectable,
  armedResumePhase,
  armedMilestoneStartIdx,
  onResumeTap,
  resumeModeActive,
  resumeHint,
  canResumeEligibility,
  resumeBlockedReason,
}: PhaseTimelineProps) {
  const hintText = resumeModeActive
    ? resumeHint ?? (canResumeEligibility ? "Tap a phase once, tap again to resume from it" : resumeBlockedReason)
    : resumeBlockedReason

  return (
    <div className="flex flex-col gap-2">
      {hintText ? (
        <p className="text-[11px] text-muted">{hintText}</p>
      ) : null}
      <HorizontalStepperContent
        phaseStates={phaseStates}
        loading={loading}
        completedWorkflow={completedWorkflow}
        canResumeFromTimeline={canResumeFromTimeline}
        isPhaseResumeSelectable={isPhaseResumeSelectable}
        armedResumePhase={armedResumePhase}
        armedMilestoneStartIdx={armedMilestoneStartIdx}
        onResumeTap={onResumeTap}
      />
    </div>
  )
}
