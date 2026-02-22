// ---------------------------------------------------------------------------
// Shared date/number formatting utilities
// ---------------------------------------------------------------------------

/**
 * Parse an ISO or SQLite-style timestamp string into a Date object.
 * SQLite timestamps are stored without "T" and without timezone suffix;
 * we treat them as UTC by appending "Z".
 */
function parseDate(raw: string): Date {
  return new Date(raw.includes("T") ? raw : raw.replace(" ", "T") + "Z")
}

/**
 * Format a timestamp for the run info strip in RunView.
 * Example: "Feb 21, 3:45 PM"
 */
export function formatRunDate(raw: string | null | undefined): string {
  if (!raw) return ""
  try {
    return parseDate(raw).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    })
  } catch {
    return raw.slice(0, 16)
  }
}

/**
 * Format a timestamp relative to today for compact sidebar labels.
 * Examples: "Today", "Yesterday", "Mon", "Feb 21"
 */
export function formatShortDate(raw: string | null | undefined): string {
  if (!raw) return ""
  try {
    const d = parseDate(raw)
    const now = new Date()
    const diffDays = Math.floor((now.getTime() - d.getTime()) / 86400000)
    if (diffDays === 0) return "Today"
    if (diffDays === 1) return "Yesterday"
    if (diffDays < 7) return d.toLocaleDateString(undefined, { weekday: "short" })
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" })
  } catch {
    return raw.slice(0, 10)
  }
}

/**
 * Format a timestamp for the HistoryView table (full date + time).
 * Example: "Feb 21, 2026, 03:45 PM"
 */
export function formatFullDate(raw: string | null | undefined): string {
  if (!raw) return "--"
  try {
    return parseDate(raw).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return raw.slice(0, 16)
  }
}

/**
 * Compute a human-readable duration between two ISO/SQLite timestamps.
 * Returns null if either timestamp is missing or parsing fails.
 */
export function formatDuration(
  start: string | null | undefined,
  end: string | null | undefined,
): string | null {
  if (!start || !end) return null
  try {
    const s = parseDate(start)
    const e = parseDate(end)
    const secs = Math.max(0, Math.round((e.getTime() - s.getTime()) / 1000))
    if (secs < 60) return `${secs}s`
    const m = Math.floor(secs / 60)
    const h = Math.floor(m / 60)
    if (h > 0) return `${h}h ${m % 60}m`
    return `${m}m ${secs % 60}s`
  } catch {
    return null
  }
}
