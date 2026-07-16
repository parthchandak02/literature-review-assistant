import { useQuery } from "@tanstack/react-query"
import {
  fetchDbCostAggregates,
  fetchDbCosts,
  fetchWorkflowValidationChecks,
  fetchWorkflowValidationSummary,
} from "@/lib/api"
import type { DbCostExportGranularity } from "@/lib/api"

export const LIVE_COST_REFRESH_MS = 5_000

export function dbCostsQueryKey(runId: string) {
  return ["dbCosts", runId] as const
}

export function dbCostAggregatesQueryKey(
  runId: string,
  startDate: string,
  endDate: string,
  granularity: DbCostExportGranularity = "day",
) {
  return ["dbCostAggregates", runId, startDate, endDate, granularity] as const
}

export function workflowValidationSummaryQueryKey(workflowId: string) {
  return ["workflowValidationSummary", workflowId] as const
}

export function workflowValidationChecksQueryKey(
  workflowId: string,
  validationRunId: string | null | undefined,
) {
  return ["workflowValidationChecks", workflowId, validationRunId ?? ""] as const
}

export function useDbCosts(
  runId: string | null | undefined,
  options?: { enabled?: boolean; isLive?: boolean },
) {
  const enabled = (options?.enabled ?? true) && Boolean(runId)
  return useQuery({
    queryKey: dbCostsQueryKey(runId ?? ""),
    queryFn: () => fetchDbCosts(runId!),
    enabled,
    refetchInterval: options?.isLive ? LIVE_COST_REFRESH_MS : false,
  })
}

export function useDbCostAggregates(
  runId: string | null | undefined,
  options: {
    enabled?: boolean
    startDate?: string
    endDate?: string
    granularity?: DbCostExportGranularity
  } = {},
) {
  const startDate = options.startDate ?? ""
  const endDate = options.endDate ?? ""
  const granularity = options.granularity ?? "day"
  const enabled = (options.enabled ?? true) && Boolean(runId)
  return useQuery({
    queryKey: dbCostAggregatesQueryKey(runId ?? "", startDate, endDate, granularity),
    queryFn: () =>
      fetchDbCostAggregates(runId!, {
        start_ts: startDate || undefined,
        end_ts: endDate || undefined,
        granularity,
      }),
    enabled,
  })
}

export function useWorkflowValidationSummary(workflowId: string | null | undefined) {
  return useQuery({
    queryKey: workflowValidationSummaryQueryKey(workflowId ?? ""),
    queryFn: () => fetchWorkflowValidationSummary(workflowId!),
    enabled: Boolean(workflowId),
    retry: false,
  })
}

export function useWorkflowValidationChecks(
  workflowId: string | null | undefined,
  validationRunId: string | null | undefined,
) {
  return useQuery({
    queryKey: workflowValidationChecksQueryKey(workflowId ?? "", validationRunId),
    queryFn: () => fetchWorkflowValidationChecks(workflowId!, validationRunId ?? undefined),
    enabled: Boolean(workflowId) && Boolean(validationRunId),
    retry: false,
  })
}

export function costsFetchErrorMessage(error: unknown): string | null {
  const msg = error instanceof Error ? error.message : String(error)
  return msg.toLowerCase().includes("failed to fetch") ? "Cannot reach backend." : msg
}
