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

/** Semantic progress-bar fill class for run cards and headers. */
export const STATUS_PROGRESS: Record<RunStatus, string> = {
  idle: "bg-surface-4",
  connecting: "bg-intent-active",
  streaming: "bg-intent-active",
  done: "bg-intent-success",
  error: "bg-intent-danger",
  cancelled: "bg-intent-warning",
  stale: "bg-intent-warning",
}

export type ScreeningDecision = "include" | "exclude" | "uncertain"

export const SCREENING_DECISION_VARIANT: Record<ScreeningDecision, BadgeVariant> = {
  include: "success",
  exclude: "danger",
  uncertain: "warning",
}

export function screeningDecisionToVariant(decision: string | null | undefined): BadgeVariant {
  if (!decision) return "neutral"
  return SCREENING_DECISION_VARIANT[decision as ScreeningDecision] ?? "neutral"
}

export function confidenceToVariant(confidence: number | null | undefined): BadgeVariant {
  if (confidence == null) return "neutral"
  const pct = Math.round(confidence * 100)
  if (pct >= 80) return "success"
  if (pct >= 60) return "warning"
  return "danger"
}

const AUDIT_STATUS_VARIANT: Record<string, BadgeVariant> = {
  passed: "success",
  blocked: "danger",
  completed_with_findings: "warning",
  review: "warning",
  pending: "neutral",
}

export function auditStatusToVariant(status: string | null | undefined): BadgeVariant {
  if (!status) return "neutral"
  return AUDIT_STATUS_VARIANT[status] ?? "neutral"
}

const PRISMA_STATUS_VARIANT: Record<string, BadgeVariant> = {
  REPORTED: "success",
  PARTIAL: "warning",
  MISSING: "danger",
  NOT_APPLICABLE: "neutral",
}

export function prismaStatusToVariant(status: string | null | undefined): BadgeVariant {
  if (!status) return "neutral"
  return PRISMA_STATUS_VARIANT[status] ?? "neutral"
}

export interface RunHeaderStatusInput {
  status: string
  isDone: boolean
  isRunning: boolean
  isCancelled: boolean
  isFailed: boolean
  isAwaitingReview: boolean
}

/** Run info strip label + text class (canonical status presentation). */
export function resolveRunHeaderStatus(input: RunHeaderStatusInput): {
  label: string
  className: string
} {
  const { status, isDone, isRunning, isCancelled, isFailed, isAwaitingReview } = input
  if (isAwaitingReview && !isDone) {
    return { label: "Awaiting Review", className: "text-intent-warning" }
  }
  if (isRunning) {
    return { label: STATUS_LABEL.streaming, className: STATUS_TEXT.streaming }
  }
  if (isCancelled) {
    return { label: STATUS_LABEL.cancelled, className: STATUS_TEXT.cancelled }
  }
  if (isFailed) {
    return { label: STATUS_LABEL.error, className: STATUS_TEXT.error }
  }
  if (status === "done" || isDone) {
    return { label: STATUS_LABEL.done, className: STATUS_TEXT.done }
  }
  return { label: STATUS_LABEL.idle, className: STATUS_TEXT.idle }
}

/** Recharts-friendly theme tokens (no hex in TSX). */
export const CHART_THEME = {
  tickFill: "var(--color-chart-tick)",
  seriesPrimary: "var(--color-chart-series)",
  cursorFill: "var(--color-chart-cursor)",
} as const

/** Canonical reason label map aligned with backend RunContext labels. */
export const REASON_LABELS: Record<string, string> = {
  insufficient_content_heuristic: "Skipped: abstract missing or too short",
  protocol_only_heuristic: "Skipped: protocol-only publication",
  fulltext_no_pdf_heuristic: "Skipped: full text PDF unavailable",
  metadata_incomplete: "Skipped: missing required metadata",
  keyword_filter: "Skipped: no intervention keyword match",
  low_relevance_score: "Skipped: low BM25 relevance score",
  batch_screened_low: "Skipped: low pre-ranker score",
  timeout: "Full text retrieval timed out",
  publisher_403: "Full text blocked by publisher",
  publisher_401: "Full text requires authentication",
  rate_limited: "Full text retrieval rate-limited",
  doi_unresolved: "DOI did not resolve to full text",
  no_pdf_signal: "No downloadable PDF detected",
  no_identifier: "No URL or DOI for full text retrieval",
  no_oa_path: "No open-access full text path found",
  oa_recovered: "Full text successfully retrieved",
  connector_degraded: "Connector degraded; fallback path used",
  no_full_text: "Full text unavailable",
  wrong_population: "Wrong population",
  wrong_intervention: "Wrong intervention",
  wrong_comparator: "Wrong comparator",
  wrong_outcome: "Wrong outcome",
  wrong_study_design: "Wrong study design",
  not_peer_reviewed: "Not peer-reviewed",
  duplicate: "Duplicate",
  insufficient_data: "Insufficient data",
  wrong_language: "Wrong language",
  protocol_only: "Protocol-only",
}

export function humanizeReason(reasonCode: string | null | undefined): string {
  if (!reasonCode) return "unspecified reason"
  return REASON_LABELS[reasonCode] ?? reasonCode.replace(/_/g, " ")
}

// ---------------------------------------------------------------------------
// Phase colors (theme-backed CSS variables) used by charts and visualizations
// ---------------------------------------------------------------------------

export const PHASE_COLOR_VARS: Record<string, string> = {
  phase_2_search: "--color-phase-2-search",
  phase_3_screening: "--color-phase-3-screening",
  screening_calibration: "--color-screening-calibration",
  fulltext_pdf_retrieval: "--color-fulltext-pdf-retrieval",
  phase_4_extraction: "--color-phase-4-extraction",
  phase_4_extraction_quality: "--color-phase-4-extraction-quality",
  phase_4b_embedding: "--color-phase-4b-embedding",
  phase_5_synthesis: "--color-phase-5-synthesis",
  phase_5b_knowledge_graph: "--color-phase-5b-knowledge-graph",
  phase_5c_pre_writing_gate: "--color-phase-5c-pre-writing-gate",
  phase_6_writing: "--color-phase-6-writing",
  phase_6_humanizer: "--color-phase-6-humanizer",
  quality_rob2: "--color-quality-rob2",
  quality_robins_i: "--color-quality-robins-i",
  quality_casp: "--color-quality-casp",
  finalize: "--color-finalize",
}

function resolvePhaseColorToken(phaseKey: string): string | null {
  const exact = PHASE_COLOR_VARS[phaseKey]
  if (exact) return exact
  for (const [key, cssVar] of Object.entries(PHASE_COLOR_VARS)) {
    if (phaseKey.startsWith(key)) return cssVar
  }
  return null
}

/** Resolve the chart color for a phase key, falling back to prefix matching. */
export function phaseColor(phase: string): string {
  const cssVar = resolvePhaseColorToken(phase)
  if (cssVar) return `var(${cssVar})`
  return "var(--color-finalize)"
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
