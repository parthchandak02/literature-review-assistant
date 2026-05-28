import type { FunnelStage } from "@/lib/funnelStages"
import type { RunStatus } from "@/lib/constants"

export interface PhaseProgress {
  value: number
  completedPhases: number
  currentPhaseFraction?: number
}

export interface LiveRun {
  runId: string
  topic: string
  status: RunStatus
  cost: number
  workflowId?: string | null
  phaseProgress?: PhaseProgress
  startedAt?: string | null
  papersFound?: number | null
  papersIncluded?: number | null
  funnelStages?: FunnelStage[]
}
