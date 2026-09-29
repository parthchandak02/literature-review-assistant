import { phaseLabel } from "@/lib/constants"
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

/** 2 decimals from $1, exactly 4 below (no trimming), and "$0.00" for zero. */
export function formatUsd(value: number): string {
  if (!Number.isFinite(value) || value === 0) return "$0.00"
  const digits = Math.abs(value) >= 1 ? 2 : 4
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value)
}

/**
 * One USD format for a whole table or chart: 4 decimals when any non-zero value is
 * below $1, otherwise 2. Keeps "$1.20" from sitting next to "$0.4097".
 */
export function usdFormatterFor(values: readonly number[]): (value: number) => string {
  const needsPrecision = values.some((v) => Number.isFinite(v) && v !== 0 && Math.abs(v) < 1)
  const formatter = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: needsPrecision ? 4 : 2,
    maximumFractionDigits: needsPrecision ? 4 : 2,
  })
  return (value: number) => formatter.format(Number.isFinite(value) ? value : 0)
}

/** Axis ticks are round numbers, so trailing zeros are trimmed down to 2 decimals. */
export function formatAxisCost(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(value)
}

const NICE_STEPS = [1, 2, 2.5, 5, 10]

/** Evenly spaced ticks from 0 that cover `max` with about `target` intervals. */
export function niceCostTicks(max: number, target = 4): number[] {
  if (!Number.isFinite(max) || max <= 0) return [0]
  const rough = max / Math.max(target, 1)
  const magnitude = 10 ** Math.floor(Math.log10(rough))
  const step = (NICE_STEPS.find((s) => s * magnitude >= rough) ?? 10) * magnitude
  const count = Math.ceil(max / step - 1e-9)
  return Array.from({ length: count + 1 }, (_, i) => Number((i * step).toPrecision(12)))
}

export { formatCount as formatInteger } from "@/lib/format"

export function formatPhaseName(phase: string): string {
  return phaseLabel(phase, "short")
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

export const fieldLabelClass = "space-y-1 text-xs"
export const fieldControlClass =
  "h-8 w-full min-w-0 rounded-control border border-border bg-card/90 px-2.5 text-xs text-foreground shadow-sm outline-none transition-colors hover:border-border focus:border-intent-primary focus-visible:ring-1 focus-visible:ring-ring"
export const statCardClass = "rounded-lg border border-border/80 bg-card/60 px-2.5 py-2"
export const sectionHeaderClass = "border-b border-border/80 px-2.5 py-1.5 text-xs font-semibold text-foreground"
/** Breakdown grid sized by its container (the Settings dialog is narrower than the page). */
export const costOpsGridClass = "grid gap-2 grid-cols-1 @2xl:grid-cols-2 @6xl:grid-cols-3"
/** 2-up grid for the per-run ops panel (phases + models). */
export const costOpsPairGridClass = "grid gap-2 grid-cols-1 md:grid-cols-2"
/** Shared segmented control chrome for presets, view mode, and actions */
export const costOpsSegmentGroupClass =
  "flex flex-wrap items-center gap-1 rounded-lg border border-border/80 bg-card/50 p-1 shrink-0"
export function costOpsSegmentButtonClass(active: boolean): string {
  return cn(
    "h-7 rounded-control px-2.5 text-xs shrink-0 inline-flex items-center gap-1.5 font-medium transition-colors",
    active
      ? "bg-intent-primary-solid text-intent-primary-solid-fg shadow-sm"
      : "text-foreground hover:bg-surface-3/80 hover:text-foreground",
  )
}
