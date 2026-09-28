import type { RunTab } from "@/context/runSessionTypes"

export type RunGate = "config_generating" | "config_ready" | "awaiting_prospero" | "awaiting_review"

export const GATE_ACTION_TAB: Record<RunGate, RunTab> = {
  config_generating: "config",
  config_ready: "config",
  awaiting_prospero: "config",
  awaiting_review: "review-screening",
}

export const DEFAULT_RUN_TAB: RunTab = "activity"

export function resolveRunGate(input: {
  status?: string | null
  historicalStatus?: string | null
  isAwaitingProspero: boolean
  isAwaitingReview: boolean
  isRunning: boolean
}): RunGate | null {
  if (input.isAwaitingReview) return "awaiting_review"
  const statuses = [input.status, input.historicalStatus].map((s) => (s ?? "").trim().toLowerCase())
  if (statuses.includes("config_generating")) return "config_generating"
  if (!input.isRunning && statuses.includes("config_ready")) return "config_ready"
  if (input.isAwaitingProspero) return "awaiting_prospero"
  return null
}

export function defaultTabForStatus(gate: RunGate | null): RunTab {
  return gate ? GATE_ACTION_TAB[gate] : DEFAULT_RUN_TAB
}

export function shouldShowGateBanner(gate: RunGate | null, activeTab: RunTab): gate is RunGate {
  return gate != null && GATE_ACTION_TAB[gate] !== activeTab
}

/** Tab to switch to when a run is opened on its default tab, or null to stay put. */
export function resolveAutoRouteTab(input: {
  gate: RunGate | null
  activeTab: RunTab
  explicitDeepLink: boolean
}): RunTab | null {
  if (input.explicitDeepLink || input.activeTab !== DEFAULT_RUN_TAB) return null
  const target = defaultTabForStatus(input.gate)
  return target === input.activeTab ? null : target
}

/** Workflow id when the pathname names a run tab explicitly (`/run/{id}/{tab}`), else null. */
export function explicitTabWorkflowId(pathname: string): string | null {
  const match = pathname.match(/^\/run\/([^/]+)\/[^/]+$/)
  return match ? match[1] : null
}

/** Place the gate tab (`review-screening`) directly after Activity when present. */
export function orderRunTabs<T extends { id: RunTab }>(base: T[], gateTab: T | null): T[] {
  if (!gateTab) return base
  const rest = base.filter((t) => t.id !== gateTab.id)
  const activityIdx = rest.findIndex((t) => t.id === "activity")
  const at = activityIdx >= 0 ? activityIdx + 1 : 0
  return [...rest.slice(0, at), gateTab, ...rest.slice(at)]
}
