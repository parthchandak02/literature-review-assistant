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

export function shouldFallbackToWorkflowEvents(
  runEventsCount: number,
  workflowId: string | null,
  runId: string,
): boolean {
  return runEventsCount === 0 && Boolean(workflowId) && workflowId !== runId
}

export function shouldUsePrefetchedHistorical(
  prefetchedHistoricalEvents: unknown[] | null | undefined,
): boolean {
  return (prefetchedHistoricalEvents?.length ?? 0) > 0
}
