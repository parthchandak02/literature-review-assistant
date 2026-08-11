import type { HistoryEntry } from "@/lib/api"
import type { SelectedRun } from "@/context/runSessionTypes"
import { isSameRunSelection, isTerminalHistoricalStatus } from "@/lib/runSelection"

/** Explicit history-sidebar selection transitions (reducer input). */
export type HistorySelectTransition =
  | { kind: "focus_same_run" }
  | { kind: "connect_live"; entry: HistoryEntry; runId: string; topic: string }
  | { kind: "attach_historical"; entry: HistoryEntry }

export interface HistorySelectContext {
  selectedRun: SelectedRun | null
  liveRunId: string | null
}

export function resolveHistorySelectTransition(
  entry: HistoryEntry,
  ctx: HistorySelectContext,
  active: { run_id: string; topic: string } | null,
): HistorySelectTransition {
  if (active) {
    if (
      isSameRunSelection(
        ctx.liveRunId,
        ctx.selectedRun?.runId,
        ctx.selectedRun?.workflowId,
        active.run_id,
        entry.workflow_id,
      )
    ) {
      return { kind: "focus_same_run" }
    }
    return {
      kind: "connect_live",
      entry,
      runId: active.run_id,
      topic: active.topic || entry.topic,
    }
  }

  if (entry.live_run_id) {
    if (
      isSameRunSelection(
        ctx.liveRunId,
        ctx.selectedRun?.runId,
        ctx.selectedRun?.workflowId,
        entry.live_run_id,
        entry.workflow_id,
      )
    ) {
      return { kind: "focus_same_run" }
    }
    return {
      kind: "connect_live",
      entry,
      runId: entry.live_run_id,
      topic: entry.topic,
    }
  }

  return { kind: "attach_historical", entry }
}

export function selectedRunFromHistoryEntry(
  entry: HistoryEntry,
  overrides: Partial<SelectedRun> & Pick<SelectedRun, "runId">,
): SelectedRun {
  const isCompleted = isTerminalHistoricalStatus(entry.status)
  return {
    runId: overrides.runId,
    workflowId: entry.workflow_id,
    topic: entry.topic,
    dbPath: entry.db_path,
    isDone: overrides.isDone ?? isCompleted,
    historicalStatus: overrides.historicalStatus ?? entry.status,
    startedAt: overrides.startedAt ?? null,
    createdAt: entry.created_at,
    papersFound: entry.papers_found ?? null,
    papersIncluded: entry.papers_included ?? null,
    historicalCost: entry.total_cost ?? null,
    attachPending: overrides.attachPending,
  }
}

export function selectedRunToHistoryEntry(selectedRun: SelectedRun | null): HistoryEntry | null {
  if (!selectedRun?.workflowId || !selectedRun.dbPath) return null
  return {
    workflow_id: selectedRun.workflowId,
    topic: selectedRun.topic,
    status: selectedRun.historicalStatus ?? "stale",
    db_path: selectedRun.dbPath,
    created_at: selectedRun.createdAt ?? new Date().toISOString(),
    papers_found: selectedRun.papersFound ?? null,
    papers_included: selectedRun.papersIncluded ?? null,
    total_cost: selectedRun.historicalCost ?? null,
    live_run_id: null,
    notes: null,
  }
}
