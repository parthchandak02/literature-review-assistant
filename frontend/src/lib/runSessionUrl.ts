import type { RunTab } from "@/views/RunView"

export const VALID_RUN_TABS = new Set<RunTab>([
  "activity",
  "results",
  "database",
  "cost",
  "config",
  "quality",
  "review-screening",
  "references",
])

export function parseRunUrl(pathname: string): { workflowId: string; tab: RunTab } | null {
  const match = pathname.match(/^\/run\/([^/]+)(?:\/([^/]+))?$/)
  if (!match) return null
  const workflowId = match[1]
  const rawTab = match[2] ?? "activity"
  const tab = VALID_RUN_TABS.has(rawTab as RunTab) ? (rawTab as RunTab) : "activity"
  return { workflowId, tab }
}
