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

export const fieldLabelClass = "space-y-1.5 text-sm"
export const fieldControlClass =
  "h-10 w-full min-w-0 rounded-lg border border-border bg-card/90 px-3 text-sm text-foreground shadow-sm outline-none transition-colors hover:border-border focus:border-intent-primary"
export const statCardClass = "rounded-xl border border-border/80 bg-card/60 px-4 py-4"
export const loadingStages = [
  "Preparing filters",
  "Fetching cost aggregates",
  "Building summaries",
  "Rendering breakdowns",
] as const
export const sectionHeaderClass = "border-b border-border/80 px-4 py-3 text-sm font-semibold text-foreground"
