// ---------------------------------------------------------------------------
// Shared constants consumed by multiple views and components.
// Single source of truth -- no per-file duplication.
// ---------------------------------------------------------------------------

export const PHASE_ORDER = [
  "phase_2_search",
  "phase_3_screening",
  "fulltext_pdf_retrieval",
  "phase_4_extraction_quality",
  "phase_4b_embedding",
  "phase_5_synthesis",
  "phase_5b_knowledge_graph",
  "phase_5c_pre_writing_gate",
  "phase_6_writing",
  "finalize",
] as const

export type PhaseKey = (typeof PHASE_ORDER)[number]

export const PHASE_LABELS: Record<string, string> = {
  start: "Start",
  phase_2_search: "Search",
  phase_3_screening: "Screening",
  screening_calibration: "Threshold Calibration",
  fulltext_pdf_retrieval: "Full-Text PDF Retrieval",
  citation_chasing: "Citation Chasing",
  phase_4_extraction_quality: "Extraction & Quality",
  phase_4b_embedding: "Embedding",
  phase_5_synthesis: "Synthesis",
  phase_5b_knowledge_graph: "Knowledge Graph",
  phase_5c_pre_writing_gate: "Pre-Writing Gate",
  phase_6_writing: "Writing",
  finalize: "Finalize",
}

export const PHASE_MILESTONES = [
  {
    key: "discovery",
    label: "Discovery",
    phases: ["phase_2_search", "phase_3_screening", "fulltext_pdf_retrieval"],
  },
  {
    key: "evidence",
    label: "Evidence Build",
    phases: ["phase_4_extraction_quality", "phase_4b_embedding"],
  },
  {
    key: "synthesis",
    label: "Synthesis",
    phases: ["phase_5_synthesis", "phase_5b_knowledge_graph", "phase_5c_pre_writing_gate"],
  },
  {
    key: "manuscript",
    label: "Manuscript",
    phases: ["phase_6_writing"],
  },
  {
    key: "finalize",
    label: "Finalize",
    phases: ["finalize"],
  },
] as const

/** Phase order for resume-from-phase (matches backend PHASE_ORDER). */
export const RESUME_PHASE_ORDER = [
  "phase_2_search",
  "phase_3_screening",
  "phase_4_extraction_quality",
  "phase_4b_embedding",
  "phase_5_synthesis",
  "phase_5b_knowledge_graph",
  "phase_5c_pre_writing_gate",
  "phase_6_writing",
  "finalize",
] as const

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

import type { BadgeVariant } from "@/components/ui/badge"

/** Canonical map from RunStatus to Badge variant. Single source of truth. */
export const STATUS_VARIANT: Record<RunStatus, BadgeVariant> = {
  idle: "neutral",
  connecting: "active",
  streaming: "active",
  done: "success",
  error: "danger",
  cancelled: "warning",
  stale: "warning",
}

/** Convenience helper — returns the Badge variant for a given status. */
export function statusToVariant(status: RunStatus): BadgeVariant {
  return STATUS_VARIANT[status] ?? "neutral"
}

/** Semantic dot color for inline status indicators. */
export const STATUS_DOT: Record<RunStatus, string> = {
  idle: "bg-intent-neutral",
  connecting: "bg-intent-active",
  streaming: "bg-intent-active",
  done: "bg-intent-success",
  error: "bg-intent-danger",
  cancelled: "bg-intent-warning",
  stale: "bg-intent-warning",
}

/** Semantic text color for status labels. */
export const STATUS_TEXT: Record<RunStatus, string> = {
  idle: "text-intent-neutral",
  connecting: "text-intent-active",
  streaming: "text-intent-active",
  done: "text-intent-success",
  error: "text-intent-danger",
  cancelled: "text-intent-warning",
  stale: "text-intent-warning",
}

// ---------------------------------------------------------------------------
// Phase colors (hex) used by charts and visualizations
// ---------------------------------------------------------------------------

export const PHASE_COLORS: Record<string, string> = {
  phase_2_search: "#3b82f6",
  phase_3_screening: "#8b5cf6",
  screening_calibration: "#a78bfa",
  fulltext_pdf_retrieval: "#c4b5fd",
  phase_4_extraction: "#f59e0b",
  phase_4_extraction_quality: "#d97706",
  phase_4b_embedding: "#f59e0b",
  phase_5_synthesis: "#10b981",
  phase_5b_knowledge_graph: "#14b8a6",
  phase_5c_pre_writing_gate: "#0f766e",
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
  screening_calibration: "Calibration",
  fulltext_pdf_retrieval: "PDF Retrieval",
  phase_4_extraction: "Extraction",
  phase_4_extraction_quality: "Ext. Quality",
  phase_4b_embedding: "Embedding",
  phase_5_synthesis: "Synthesis",
  phase_5b_knowledge_graph: "K. Graph",
  phase_5c_pre_writing_gate: "Pre-Write",
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
