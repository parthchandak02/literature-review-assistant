function toNumber(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number(value)
    return Number.isFinite(n) ? n : null
  }
  return null
}

/** Effect sizes, CI bounds and N: integers as-is, otherwise two decimals; non-numeric text passes through. */
export function formatStat(value: unknown): string {
  if (value == null || value === "") return "–"
  const n = toNumber(value)
  if (n == null) return String(value)
  return Number.isInteger(n) ? n.toLocaleString() : n.toFixed(2)
}

/** APA-style p-values: `<0.001` below the floor, otherwise three decimals. */
export function formatPValue(value: unknown): string {
  if (value == null || value === "") return "–"
  const n = toNumber(value)
  if (n == null) return String(value)
  if (n < 0.001) return "<0.001"
  return n.toFixed(3)
}

export function formatCi(lower: unknown, upper: unknown): string {
  if (lower == null || upper == null || lower === "" || upper === "") return "–"
  return `${formatStat(lower)} to ${formatStat(upper)}`
}
