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

// ---------------------------------------------------------------------------
// Phase colors (hex) used by charts and visualizations
// ---------------------------------------------------------------------------

export const PHASE_COLORS: Record<string, string> = {
  phase_2_search: "#3b82f6",
  phase_3_screening: "#8b5cf6",
  phase_4_extraction: "#f59e0b",
  phase_4_extraction_quality: "#d97706",
  phase_5_synthesis: "#10b981",
  phase_6_writing: "#ef4444",
  phase_6_humanizer: "#f97316",
  quality_rob2: "#06b6d4",
  quality_robins_i: "#0ea5e9",
  quality_casp: "#38bdf8",
  finalize: "#6b7280",
}

/** Resolve the chart color for a phase key, falling back to prefix matching. */
export function phaseColor(phase: string): string {
  if (phase in PHASE_COLORS) return PHASE_COLORS[phase]
  for (const [key, color] of Object.entries(PHASE_COLORS)) {
    if (phase.startsWith(key)) return color
  }
  return "#6b7280"
}

export const PHASE_LABEL_MAP: Record<string, string> = {
  phase_2_search: "Search",
  phase_3_screening: "Screening",
  phase_4_extraction: "Extraction",
  phase_4_extraction_quality: "Ext. Quality",
  phase_5_synthesis: "Synthesis",
  phase_6_writing: "Writing",
  phase_6_humanizer: "Humanizer",
  quality_rob2: "RoB 2",
  quality_robins_i: "ROBINS-I",
  quality_casp: "CASP",
  finalize: "Finalize",
}

// ---------------------------------------------------------------------------

/** Map raw backend/SSE status strings to the canonical RunStatus. */
export function resolveRunStatus(raw: string | null | undefined): RunStatus {
  const s = (raw ?? "").toLowerCase()
  if (s === "completed" || s === "done") return "done"
  if (s === "running" || s === "streaming") return "streaming"
  if (s === "connecting") return "connecting"
  if (s === "error" || s === "failed") return "error"
  if (s === "cancelled" || s === "canceled" || s === "interrupted") return "cancelled"
  if (s === "stale") return "stale"
  if (s === "awaiting_review") return "streaming"
  return "idle"
}
