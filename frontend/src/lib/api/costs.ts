import { apiFetch } from "./client"
import { API_BASE } from "./internal"

export interface DbCostRow {
  model: string
  phase: string
  calls: number
  tokens_in: number
  tokens_out: number
  cost_usd: number
  avg_latency_ms: number | null
}

export interface DbCostAggregateBucketRow {
  bucket: string
  calls: number
  tokens_in: number
  tokens_out: number
  cost_usd: number
}

export interface DbCostAggregateGroupRow {
  group_key: string
  calls: number
  tokens_in: number
  tokens_out: number
  cost_usd: number
}

export interface DbCostAggregateTotals {
  total_cost_usd: number
  total_calls: number
  total_tokens_in: number
  total_tokens_out: number
}

export interface DbCostAggregatesResponse {
  run_id: string
  start_ts: string | null
  end_ts: string | null
  totals: DbCostAggregateTotals
  by_day: DbCostAggregateBucketRow[]
  by_week: DbCostAggregateBucketRow[]
  by_month: DbCostAggregateBucketRow[]
  by_workflow: DbCostAggregateGroupRow[]
  by_phase: DbCostAggregateGroupRow[]
  by_model: DbCostAggregateGroupRow[]
}

export interface HistoryCostAggregatesResponse {
  run_root: string
  start_ts: string | null
  end_ts: string | null
  include_archived: boolean
  workflow_count: number
  totals: DbCostAggregateTotals
  by_day: DbCostAggregateBucketRow[]
  by_week: DbCostAggregateBucketRow[]
  by_month: DbCostAggregateBucketRow[]
  by_workflow: DbCostAggregateGroupRow[]
  by_phase: DbCostAggregateGroupRow[]
  by_model: DbCostAggregateGroupRow[]
}

export type DbCostExportGranularity = "day" | "week" | "month"

export interface DbCostAggregateParams {
  start_ts?: string
  end_ts?: string
  granularity?: DbCostExportGranularity
}

export interface DbCostExportParams extends DbCostAggregateParams {
  granularity?: DbCostExportGranularity
}

export interface HistoryCostAggregateParams extends DbCostAggregateParams {
  run_root?: string
  include_archived?: boolean
}

export interface HistoryCostExportParams extends HistoryCostAggregateParams {
  granularity?: DbCostExportGranularity
}

export interface ScreeningDiagnostics {
  batch_parse_degraded: number
  batch_id_mismatch: number
  batch_missing_fallback: number
  contract_violation_count: number
  fast_path_include: number
  fast_path_exclude: number
  cross_reviewed: number
}

export async function fetchDbCosts(
  runId: string,
): Promise<{ total_cost: number; records: DbCostRow[]; screening_diagnostics?: ScreeningDiagnostics }> {
  return apiFetch(`/db/${runId}/costs`)
}

export async function fetchDbCostAggregates(
  runId: string,
  params?: DbCostAggregateParams,
): Promise<DbCostAggregatesResponse> {
  const qs = new URLSearchParams()
  if (params?.start_ts) qs.set("start_ts", params.start_ts)
  if (params?.end_ts) qs.set("end_ts", params.end_ts)
  if (params?.granularity) qs.set("granularity", params.granularity)
  const suffix = qs.toString() ? `?${qs.toString()}` : ""
  return apiFetch(`/db/${runId}/costs/aggregates${suffix}`)
}

export function getDbCostExportUrl(runId: string, params?: DbCostExportParams): string {
  const qs = new URLSearchParams()
  if (params?.start_ts) qs.set("start_ts", params.start_ts)
  if (params?.end_ts) qs.set("end_ts", params.end_ts)
  if (params?.granularity) qs.set("granularity", params.granularity)
  const suffix = qs.toString() ? `?${qs.toString()}` : ""
  return `${API_BASE}/db/${runId}/costs/export${suffix}`
}

export async function fetchHistoryCostAggregates(
  params?: HistoryCostAggregateParams,
  options?: { signal?: AbortSignal },
): Promise<HistoryCostAggregatesResponse> {
  const qs = new URLSearchParams()
  if (params?.run_root) qs.set("run_root", params.run_root)
  if (params?.start_ts) qs.set("start_ts", params.start_ts)
  if (params?.end_ts) qs.set("end_ts", params.end_ts)
  if (params?.include_archived !== undefined) {
    qs.set("include_archived", String(params.include_archived))
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : ""
  return apiFetch(`/history/costs/aggregates${suffix}`, {
    cache: "no-store",
    signal: options?.signal,
  })
}

export function getHistoryCostExportUrl(params?: HistoryCostExportParams): string {
  const qs = new URLSearchParams()
  if (params?.run_root) qs.set("run_root", params.run_root)
  if (params?.start_ts) qs.set("start_ts", params.start_ts)
  if (params?.end_ts) qs.set("end_ts", params.end_ts)
  if (params?.granularity) qs.set("granularity", params.granularity)
  if (params?.include_archived !== undefined) {
    qs.set("include_archived", String(params.include_archived))
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : ""
  return `${API_BASE}/history/costs/export${suffix}`
}
