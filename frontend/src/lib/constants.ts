// ---------------------------------------------------------------------------
// Shared constants consumed by multiple views and components.
// Single source of truth -- no per-file duplication.
// ---------------------------------------------------------------------------

export const PHASE_ORDER = [
  "phase_2_search",
  "phase_3_screening",
  "phase_4_extraction_quality",
  "phase_5_synthesis",
  "phase_6_writing",
  "finalize",
] as const

export type PhaseKey = (typeof PHASE_ORDER)[number]

export const PHASE_LABELS: Record<string, string> = {
  phase_2_search: "Search",
  phase_3_screening: "Screening",
  phase_4_extraction_quality: "Extraction & Quality",
  phase_5_synthesis: "Synthesis",
  phase_6_writing: "Writing",
  finalize: "Finalize",
}

// ---------------------------------------------------------------------------
// Run status
// ---------------------------------------------------------------------------

export type RunStatus =
  | "idle"
  | "connecting"
  | "streaming"
  | "done"
  | "error"
  | "cancelled"
  | "stale"

export const STATUS_LABEL: Record<RunStatus, string> = {
  idle: "Ready",
  connecting: "Connecting",
  streaming: "Running",
  done: "Completed",
  error: "Failed",
  cancelled: "Cancelled",
  stale: "Stale",
}

export const STATUS_DOT: Record<RunStatus, string> = {
  idle: "bg-zinc-600",
  connecting: "bg-violet-400",
  streaming: "bg-violet-500",
  done: "bg-emerald-500",
  error: "bg-red-500",
  cancelled: "bg-amber-500",
  stale: "bg-amber-600",
}

export const STATUS_TEXT: Record<RunStatus, string> = {
  idle: "text-zinc-500",
  connecting: "text-violet-400",
  streaming: "text-violet-400",
  done: "text-emerald-400",
  error: "text-red-400",
  cancelled: "text-amber-400",
  stale: "text-amber-500",
}

export const STATUS_BORDER: Record<RunStatus, string> = {
  idle: "border-zinc-700",
  connecting: "border-violet-500",
  streaming: "border-violet-500",
  done: "border-emerald-500",
  error: "border-red-500",
  cancelled: "border-amber-500",
  stale: "border-amber-600",
}

export const BADGE_STYLE: Record<RunStatus, string> = {
  idle: "text-zinc-400 bg-zinc-800/60 border-zinc-700",
  connecting: "text-violet-400 bg-violet-500/10 border-violet-500/20",
  streaming: "text-amber-400 bg-amber-500/10 border-amber-500/20",
  done: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
  error: "text-red-400 bg-red-500/10 border-red-500/20",
  cancelled: "text-zinc-400 bg-zinc-800/60 border-zinc-700",
  stale: "text-amber-500 bg-amber-500/10 border-amber-500/30",
}

/** Map raw backend/SSE status strings to the canonical RunStatus. */
export function resolveRunStatus(raw: string | null | undefined): RunStatus {
  const s = (raw ?? "").toLowerCase()
  if (s === "completed" || s === "done") return "done"
  if (s === "running" || s === "streaming") return "streaming"
  if (s === "connecting") return "connecting"
  if (s === "error" || s === "failed") return "error"
  if (s === "cancelled" || s === "canceled" || s === "interrupted") return "cancelled"
  if (s === "stale") return "stale"
  return "idle"
}
