import { PHASE_LABEL_MAP } from "@/lib/constants"
import { cn } from "@/lib/utils"

export function toDateInputValue(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

export function buildPresetRange(days: number): { startDate: string; endDate: string } {
  const end = new Date()
  const start = new Date(end)
  start.setDate(end.getDate() - (days - 1))
  return {
    startDate: toDateInputValue(start),
    endDate: toDateInputValue(end),
  }
}

export type CostOpsPresetKey = "all" | "5d" | "30d" | "90d" | "custom"

export function buildAllRange(): { startDate: string; endDate: string } {
  return { startDate: "", endDate: "" }
}

export function resolveCostOpsPreset(
  preset: Exclude<CostOpsPresetKey, "custom">,
): { startDate: string; endDate: string } {
  if (preset === "all") return buildAllRange()
  const days = preset === "5d" ? 5 : preset === "30d" ? 30 : 90
  return buildPresetRange(days)
}

export function toApiStart(date: string): string | undefined {
  return date ? `${date} 00:00:00` : undefined
}

export function toApiEnd(date: string): string | undefined {
  return date ? `${date} 23:59:59` : undefined
}

export function formatUsd(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: value >= 1 ? 2 : 4,
    maximumFractionDigits: 4,
  }).format(value)
}

export function formatAxisCost(value: number): string {
  return `$${value >= 1 ? value.toFixed(2) : value.toFixed(4)}`
}

export function formatInteger(value: number): string {
  return new Intl.NumberFormat("en-US").format(value)
}

export function formatPhaseName(phase: string): string {
  if (phase in PHASE_LABEL_MAP) return PHASE_LABEL_MAP[phase]
  return phase
    .replace(/^phase_\d+_/, "")
    .replace(/^quality_/, "")
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ")
}

export const fieldLabelClass = "space-y-1 text-xs"
export const fieldControlClass =
  "h-8 w-full min-w-0 rounded-md border border-border bg-card/90 px-2.5 text-xs text-foreground shadow-sm outline-none transition-colors hover:border-border focus:border-intent-primary"
export const statCardClass = "rounded-lg border border-border/80 bg-card/60 px-2.5 py-2"
export const loadingStages = [
  "Preparing filters",
  "Fetching cost aggregates",
  "Building summaries",
  "Rendering breakdowns",
] as const
export const sectionHeaderClass = "border-b border-border/80 px-2.5 py-1.5 text-xs font-semibold text-foreground"
/** 3-up grid for cost breakdown panels; fits 6 sections in 2 rows on wide layouts */
export const costOpsGridClass = "grid gap-2 grid-cols-2 md:grid-cols-3"
/** Shared segmented control chrome for presets, view mode, and actions */
export const costOpsSegmentGroupClass =
  "flex flex-wrap items-center gap-1 rounded-lg border border-border/80 bg-card/50 p-1 shrink-0"
export function costOpsSegmentButtonClass(active: boolean): string {
  return cn(
    "h-7 rounded-md px-2.5 text-xs shrink-0 inline-flex items-center gap-1.5 font-medium transition-colors",
    active
      ? "bg-intent-primary text-primary-foreground shadow-sm"
      : "text-foreground hover:bg-surface-3/80 hover:text-foreground",
  )
}
