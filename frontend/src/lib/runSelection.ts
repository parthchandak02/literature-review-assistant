export function isSameRunSelection(
  currentLiveRunId: string | null,
  currentSelectedRunId: string | null | undefined,
  currentSelectedWorkflowId: string | null | undefined,
  targetRunId: string,
  targetWorkflowId: string,
): boolean {
  return (
    currentLiveRunId === targetRunId &&
    currentSelectedRunId === targetRunId &&
    currentSelectedWorkflowId === targetWorkflowId
  )
}

/** Use workflow-scoped replay when in-memory run replay is empty or not yet attached. */
export function shouldFallbackToWorkflowEvents(
  runEventsCount: number,
  workflowId: string | null,
): boolean {
  return runEventsCount === 0 && Boolean(workflowId)
}

export function isSameWorkflowSelection(
  currentWorkflowId: string | null | undefined,
  targetWorkflowId: string,
): boolean {
  return Boolean(currentWorkflowId) && currentWorkflowId === targetWorkflowId
}

export function shouldUsePrefetchedHistorical(
  prefetchedHistoricalEvents: unknown[] | null | undefined,
): boolean {
  return (prefetchedHistoricalEvents?.length ?? 0) > 0
}

/** Show timeline skeleton only while loading and no replayed events are available yet. */
export function shouldShowHistoricalLoading(
  historicalEventsLoading: boolean,
  loadingHistory: boolean,
  activeEventCount: number,
): boolean {
  return (historicalEventsLoading || loadingHistory) && activeEventCount === 0
}

export function isTerminalHistoricalStatus(status: string | null | undefined): boolean {
  const normalized = (status ?? "").toLowerCase()
  return ["cancelled", "done", "completed", "interrupted", "stale", "failed", "error"].includes(normalized)
}
