import { canonicalPhaseId, phaseLabel, phaseTitle } from "@/lib/constants"
import { shortModelName } from "@/lib/humanize"

export interface CostRow {
  label: string
  calls: number
  cost_usd: number
  /** Stable id when labels can collide (e.g. review topics). */
  key?: string
  /** Secondary line under the label (provider, review id). */
  sublabel?: string
  /** Full hover text; defaults to the label. */
  title?: string
}

export interface CostShareRow<T> {
  row: T
  share: number
}

export function sortByCostDesc<T extends { cost_usd: number }>(rows: readonly T[]): T[] {
  return rows.slice().sort((a, b) => b.cost_usd - a.cost_usd)
}

export function withShare<T extends { cost_usd: number }>(
  rows: readonly T[],
  total?: number,
): CostShareRow<T>[] {
  const sum = total ?? rows.reduce((acc, r) => acc + r.cost_usd, 0)
  return rows.map((row) => ({ row, share: sum > 0 ? row.cost_usd / sum : 0 }))
}

export function formatShare(share: number): string {
  if (share <= 0) return "0%"
  if (share < 0.01) return "<1%"
  return `${Math.round(share * 100)}%`
}

export const OTHER_LABEL = "Other"

export function bucketOther(
  rows: readonly CostRow[],
  maxRows: number,
  otherLabel = OTHER_LABEL,
): { rows: CostRow[]; otherCount: number } {
  if (rows.length <= maxRows) return { rows: rows.slice(), otherCount: 0 }
  const keep = Math.max(1, maxRows - 1)
  const head = rows.slice(0, keep)
  const tail = rows.slice(keep)
  const other = tail.reduce<CostRow>(
    (acc, r) => ({ label: acc.label, calls: acc.calls + r.calls, cost_usd: acc.cost_usd + r.cost_usd }),
    { label: `${otherLabel} (${tail.length})`, calls: 0, cost_usd: 0 },
  )
  return { rows: [...head, other], otherCount: tail.length }
}

export function lastN<T>(rows: readonly T[], n: number): { rows: T[]; hidden: number } {
  if (rows.length <= n) return { rows: rows.slice(), hidden: 0 }
  return { rows: rows.slice(-n), hidden: rows.length - n }
}

export function costPerUnit(totalCost: number, count: number | null | undefined, per = 1): number | null {
  if (count == null || !Number.isFinite(count) || count <= 0) return null
  if (!Number.isFinite(totalCost) || totalCost <= 0) return null
  return (totalCost / count) * per
}

export { formatCompact } from "@/lib/format"

/** Short phase labels, falling back to the long label when two phases share a short one. */
export function phaseDisplayLabels(phases: readonly string[]): Map<string, string> {
  const shortCounts = new Map<string, number>()
  for (const p of phases) {
    const s = phaseLabel(p, "short")
    shortCounts.set(s, (shortCounts.get(s) ?? 0) + 1)
  }
  const out = new Map<string, string>()
  for (const p of phases) {
    const s = phaseLabel(p, "short")
    out.set(p, (shortCounts.get(s) ?? 0) > 1 ? phaseLabel(p, "long") : s)
  }
  return out
}

export interface PhaseCostRow {
  phase: string
  label: string
  title?: string
  calls: number
  cost_usd: number
  share: number
}

export interface PhaseCostInput {
  phase: string
  calls: number
  cost_usd: number
  tokens_in?: number
  tokens_out?: number
}

/** Merge alias phase ids into their canonical id, summing cost, calls and tokens. */
export function mergePhaseAliases<T extends PhaseCostInput>(rows: readonly T[]): T[] {
  const merged = new Map<string, T>()
  for (const row of rows) {
    const phase = canonicalPhaseId(row.phase)
    const prev = merged.get(phase)
    if (!prev) {
      merged.set(phase, { ...row, phase })
      continue
    }
    const next: T = {
      ...prev,
      calls: prev.calls + row.calls,
      cost_usd: prev.cost_usd + row.cost_usd,
    }
    if (prev.tokens_in != null || row.tokens_in != null) next.tokens_in = (prev.tokens_in ?? 0) + (row.tokens_in ?? 0)
    if (prev.tokens_out != null || row.tokens_out != null) next.tokens_out = (prev.tokens_out ?? 0) + (row.tokens_out ?? 0)
    merged.set(phase, next)
  }
  return [...merged.values()]
}

export function buildPhaseCostRows(
  byPhase: readonly PhaseCostInput[],
  total?: number,
): PhaseCostRow[] {
  const sorted = sortByCostDesc(mergePhaseAliases(byPhase))
  const labels = phaseDisplayLabels(sorted.map((p) => p.phase))
  return withShare(sorted, total).map(({ row, share }) => ({
    phase: row.phase,
    label: labels.get(row.phase) ?? row.phase,
    title: phaseTitle(row.phase),
    calls: row.calls,
    cost_usd: row.cost_usd,
    share,
  }))
}

export type CostRunState = "not_started" | "running" | "finished"

export function costEmptyHeading(state: CostRunState): string {
  if (state === "finished") return "This run finished without recording any LLM calls."
  if (state === "running") return "Cost data will appear after the first LLM call completes."
  return "Cost data will appear once the review starts."
}

export interface CostGroupLabel {
  label: string
  sublabel?: string
  title?: string
}

/** `accounts/fireworks/models/deepseek-v4-pro-0813` -> deepseek-v4-pro, provider underneath. */
const MODEL_CHANNEL_SUFFIX = /-(preview|exp|experimental|latest)$/i

/** Model id as a one-line label; a release-channel suffix like "-preview" moves to the sublabel. */
export function describeModelGroup(key: string): CostGroupLabel {
  const { name, provider } = shortModelName(key)
  const base = name || key
  const channel = MODEL_CHANNEL_SUFFIX.exec(base)
  const label = channel ? base.slice(0, channel.index) : base
  const sublabel = [provider, channel?.[1].toLowerCase()].filter(Boolean).join(" · ")
  return { label, sublabel: sublabel || undefined, title: key }
}

/** Review topic as the label with the workflow id underneath; falls back to the id. */
export function describeReviewGroup(workflowId: string, topic: string | null | undefined): CostGroupLabel {
  const cleanTopic = topic?.trim()
  if (!cleanTopic) return { label: workflowId, title: workflowId }
  return { label: cleanTopic, sublabel: workflowId, title: `${cleanTopic} (${workflowId})` }
}

/**
 * Greedy wrap for SVG axis labels. Breaks at spaces and after hyphens or slashes,
 * hard-breaks tokens longer than a line, and ends the last line with "…" on overflow.
 */
export function wrapLabel(text: string, maxChars: number, maxLines = 2): string[] {
  const width = Math.max(4, Math.floor(maxChars))
  const tokens = text.trim().split(/(?<=[-/])|\s+/).filter(Boolean)
  const lines: string[] = []
  let current = ""
  const push = () => {
    if (current) lines.push(current.trimEnd())
    current = ""
  }
  for (const raw of tokens) {
    let token = raw
    while (token.length > width) {
      push()
      lines.push(token.slice(0, width))
      token = token.slice(width)
    }
    const joiner = current && !/[-/]$/.test(current) ? " " : ""
    if ((current + joiner + token).length > width) {
      push()
      current = token
    } else {
      current += joiner + token
    }
  }
  push()
  if (lines.length <= maxLines) return lines
  const kept = lines.slice(0, maxLines)
  const last = kept[maxLines - 1]
  kept[maxLines - 1] = `${last.slice(0, Math.max(1, width - 1)).trimEnd()}…`
  return kept
}
