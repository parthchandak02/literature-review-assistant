import { canonicalPhaseId, phaseLabel } from "@/lib/constants"

export interface CostRow {
  label: string
  calls: number
  cost_usd: number
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

const compactFormatter = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
})

export function formatCompact(value: number): string {
  if (Math.abs(value) < 1000) return new Intl.NumberFormat("en-US").format(value)
  return compactFormatter.format(value)
}

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
