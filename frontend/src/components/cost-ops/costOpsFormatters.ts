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

export type CostOpsSpendGranularity = "day" | "week" | "month"

export const COST_OPS_SPEND_GRANULARITIES: CostOpsSpendGranularity[] = ["day", "week", "month"]

export function costOpsSpendGranularityLabel(granularity: CostOpsSpendGranularity): string {
  if (granularity === "day") return "Day"
  if (granularity === "week") return "Week"
  return "Month"
}

function parseDayBucket(bucket: string): Date | null {
  const match = bucket.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!match) return null
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const date = new Date(year, month - 1, day)
  if (
    date.getFullYear() !== year
    || date.getMonth() !== month - 1
    || date.getDate() !== day
  ) {
    return null
  }
  return date
}

function parseMonthBucket(bucket: string): Date | null {
  const match = bucket.match(/^(\d{4})-(\d{2})$/)
  if (!match) return null
  const year = Number(match[1])
  const month = Number(match[2])
  if (month < 1 || month > 12) return null
  return new Date(year, month - 1, 1)
}

function parseWeekBucket(bucket: string): { year: number; week: number } | null {
  const match = bucket.match(/^(\d{4})-W(\d{2})$/)
  if (!match) return null
  return { year: Number(match[1]), week: Number(match[2]) }
}

/** SQLite %W week bucket: week 0 is before the first Sunday; week 1 starts on that Sunday. */
export function sqliteWeekStart(year: number, week: number): Date {
  if (week === 0) return new Date(year, 0, 1)
  const firstSunday = new Date(year, 0, 1)
  while (firstSunday.getDay() !== 0) {
    firstSunday.setDate(firstSunday.getDate() + 1)
  }
  const start = new Date(firstSunday)
  start.setDate(firstSunday.getDate() + (week - 1) * 7)
  return start
}

function formatShortDate(date: Date, includeYear = false): string {
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    ...(includeYear ? { year: "numeric" } : {}),
  })
}

function shouldIncludeYear(date: Date): boolean {
  return date.getFullYear() !== new Date().getFullYear()
}

/** Compact label for chart x-axis ticks. */
export function formatSpendBucketAxisLabel(
  bucket: string,
  granularity: CostOpsSpendGranularity,
): string {
  if (granularity === "day") {
    const date = parseDayBucket(bucket)
    if (!date) return bucket
    return formatShortDate(date, shouldIncludeYear(date))
  }

  if (granularity === "month") {
    const date = parseMonthBucket(bucket)
    if (!date) return bucket
    return date.toLocaleDateString("en-US", {
      month: "short",
      year: shouldIncludeYear(date) ? "2-digit" : undefined,
    })
  }

  const week = parseWeekBucket(bucket)
  if (!week) return bucket
  const start = sqliteWeekStart(week.year, week.week)
  const end = new Date(start)
  end.setDate(start.getDate() + 6)
  const includeYear = shouldIncludeYear(start) || start.getFullYear() !== end.getFullYear()
  if (start.getMonth() === end.getMonth()) {
    const month = start.toLocaleDateString("en-US", { month: "short" })
    return includeYear
      ? `${month} ${start.getDate()}-${end.getDate()}, ${String(start.getFullYear()).slice(-2)}`
      : `${month} ${start.getDate()}-${end.getDate()}`
  }
  const startLabel = formatShortDate(start, includeYear)
  const endLabel = formatShortDate(end, includeYear && start.getFullYear() !== end.getFullYear())
  return `${startLabel}-${endLabel}`
}

/** Full label for tables and tooltips. */
export function formatSpendBucketLabel(
  bucket: string,
  granularity: CostOpsSpendGranularity,
): string {
  if (granularity === "day") {
    const date = parseDayBucket(bucket)
    if (!date) return bucket
    return date.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
      year: "numeric",
    })
  }

  if (granularity === "month") {
    const date = parseMonthBucket(bucket)
    if (!date) return bucket
    return date.toLocaleDateString("en-US", { month: "long", year: "numeric" })
  }

  const week = parseWeekBucket(bucket)
  if (!week) return bucket
  const start = sqliteWeekStart(week.year, week.week)
  const end = new Date(start)
  end.setDate(start.getDate() + 6)
  return `${formatShortDate(start, true)} – ${formatShortDate(end, true)}`
}

export type CostOpsGroupAxisKind = "workflow" | "model" | "phase" | "generic"

function truncateAxisLabel(label: string, maxLength: number): string {
  if (label.length <= maxLength) return label
  return `${label.slice(0, maxLength - 1)}…`
}

/** Short x-axis labels for narrow breakdown charts (workflows, phases, models). */
export function formatCostGroupAxisLabel(
  label: string,
  kind: CostOpsGroupAxisKind = "generic",
): string {
  if (kind === "workflow") {
    const short = label.replace(/^wf-/i, "")
    return truncateAxisLabel(short, 10)
  }

  if (kind === "model") {
    const tail = label.split(/[:/]/).pop() ?? label
    return truncateAxisLabel(tail, 12)
  }

  if (kind === "phase") {
    const words = label.split(/\s+/)
    if (words.length === 1) return truncateAxisLabel(label, 12)
    return truncateAxisLabel(words.map((word) => word.slice(0, 4)).join(" "), 14)
  }

  return truncateAxisLabel(label, 12)
}

export const fieldLabelClass = "space-y-1 text-xs"
export const fieldControlClass =
  "h-8 w-full min-w-0 rounded-md border border-border bg-card/90 px-2.5 text-xs text-foreground shadow-sm outline-none transition-colors hover:border-border focus:border-intent-primary"
export const statCardClass = "rounded-lg border border-border/80 bg-card/60 px-2.5 py-2"
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
