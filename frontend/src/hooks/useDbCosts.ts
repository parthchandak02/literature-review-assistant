import { useQuery } from "@tanstack/react-query"
import {
  fetchDbCostAggregates,
  fetchDbCostDashboard,
  fetchDbCosts,
  fetchWorkflowValidationChecks,
  fetchWorkflowValidationSummary,
  fetchWorkflowValidationSummaryWithChecks,
} from "@/lib/api"
import type { DbCostExportGranularity } from "@/lib/api"
import { toApiEnd, toApiStart } from "@/components/cost-ops/costOpsFormatters"
import { LIVE_COST_REFRESH_MS, resolveLiveQueryRefetchInterval } from "@/lib/pollingBackoff"

export { LIVE_COST_REFRESH_MS }

export function dbCostsQueryKey(runId: string) {
  return ["dbCosts", runId] as const
}

export function dbCostDashboardQueryKey(runId: string) {
  return ["dbCostDashboard", runId] as const
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

export function workflowValidationSummaryWithChecksQueryKey(workflowId: string) {
  return ["workflowValidationSummaryWithChecks", workflowId] as const
}

export function workflowValidationChecksQueryKey(
  workflowId: string,
  validationRunId: string | null | undefined,
) {
  return ["workflowValidationChecks", workflowId, validationRunId ?? ""] as const
}

export function useDbCosts(
  runId: string | null | undefined,
  options?: { enabled?: boolean; isLive?: boolean; isSSEConnected?: boolean },
) {
  const enabled = (options?.enabled ?? true) && Boolean(runId)
  return useQuery({
    queryKey: dbCostsQueryKey(runId ?? ""),
    queryFn: () => fetchDbCosts(runId!),
    enabled,
    refetchInterval: resolveLiveQueryRefetchInterval(LIVE_COST_REFRESH_MS, {
      isLive: Boolean(options?.isLive),
      isSSEConnected: options?.isSSEConnected,
    }),
    refetchIntervalInBackground: false,
  })
}

export function useDbCostDashboard(
  runId: string | null | undefined,
  options?: { enabled?: boolean; isLive?: boolean; isSSEConnected?: boolean },
) {
  const enabled = (options?.enabled ?? true) && Boolean(runId)
  return useQuery({
    queryKey: dbCostDashboardQueryKey(runId ?? ""),
    queryFn: () => fetchDbCostDashboard(runId!),
    enabled,
    refetchInterval: resolveLiveQueryRefetchInterval(LIVE_COST_REFRESH_MS, {
      isLive: Boolean(options?.isLive),
      isSSEConnected: options?.isSSEConnected,
    }),
    refetchIntervalInBackground: false,
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
        start_ts: toApiStart(startDate),
        end_ts: toApiEnd(endDate),
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

export function useWorkflowValidationSummaryWithChecks(workflowId: string | null | undefined) {
  return useQuery({
    queryKey: workflowValidationSummaryWithChecksQueryKey(workflowId ?? ""),
    queryFn: () => fetchWorkflowValidationSummaryWithChecks(workflowId!),
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
