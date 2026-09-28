import type { FunnelStage } from "@/lib/funnelStages"
import type { RunStatus } from "@/lib/constants"
import type { LaneOverride } from "@/lib/api"

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

/**
 * Extra context for a sidebar lane change. `undo` marks the Undo toast path, which reselects
 * the review the user was viewing when they archived it. `lane` is the lane pin to restore.
 */
export interface LaneChangeOptions {
  undo?: boolean
  lane?: LaneOverride | null
}
