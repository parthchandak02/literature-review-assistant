// ---------------------------------------------------------------------------
// Shared constants consumed by multiple views and components.
// Single source of truth -- no per-file duplication.
// ---------------------------------------------------------------------------

export const PHASE_ORDER = [
  "phase_1_prospero_gate",
  "phase_2_search",
  "phase_3_screening",
  "fulltext_pdf_retrieval",
  "phase_4_extraction_quality",
  "phase_4b_embedding",
  "phase_5_synthesis",
  "phase_5b_knowledge_graph",
  "phase_5c_pre_writing_gate",
  "phase_6_writing",
  "phase_7_audit",
  "finalize",
] as const

export type PhaseKey = (typeof PHASE_ORDER)[number]

export const PHASE_MILESTONES = [
  {
    key: "start",
    label: "Start",
    phases: ["start"],
  },
  {
    key: "prospero",
    label: "PROSPERO",
    phases: ["phase_1_prospero_gate"],
  },
  {
    key: "discovery",
    label: "Discovery",
    phases: ["phase_2_search", "phase_3_screening", "fulltext_pdf_retrieval"],
  },
  {
    key: "evidence",
    label: "Evidence build",
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
    phases: ["phase_7_audit", "finalize"],
  },
] as const

export type PhaseMilestoneKey = (typeof PHASE_MILESTONES)[number]["key"]
export type MilestoneId = PhaseMilestoneKey

export type PhaseMilestone = (typeof PHASE_MILESTONES)[number]

export interface PhaseMeta {
  short: string
  long: string
  milestone: MilestoneId
}

/**
 * Single source of truth for phase labels and milestone membership.
 * Covers timeline phases, sub-phase checkpoints, and cost-record phase keys.
 */
const PHASE_META_TABLE = {
  start: { short: "Start", long: "Start", milestone: "start" },
  resume: { short: "Resume", long: "Resuming run", milestone: "start" },
  phase_1_prospero_gate: { short: "PROSPERO", long: "PROSPERO registration", milestone: "prospero" },
  phase_2_search: { short: "Search", long: "Literature search", milestone: "discovery" },
  phase_3_screening: { short: "Screening", long: "Study screening", milestone: "discovery" },
  screening_calibration: { short: "Calibration", long: "Threshold calibration", milestone: "discovery" },
  screening_batch_ranker: { short: "Pre-ranking", long: "Batch relevance pre-ranking", milestone: "discovery" },
  criteria_refinement: { short: "Criteria", long: "Criteria refinement", milestone: "discovery" },
  human_review_checkpoint: { short: "Human review", long: "Human review checkpoint", milestone: "discovery" },
  phase_3b_fulltext: { short: "Full-text screen", long: "Full-text screening", milestone: "discovery" },
  fulltext_pdf_retrieval: { short: "PDF retrieval", long: "Full-text PDF retrieval", milestone: "discovery" },
  citation_chasing: { short: "Citation chasing", long: "Citation chasing", milestone: "discovery" },
  phase_3_screening_citation_chasing: {
    short: "Citation chasing",
    long: "Citation chasing screening",
    milestone: "discovery",
  },
  phase_4_extraction_quality: {
    short: "Extraction",
    long: "Data extraction and quality appraisal",
    milestone: "evidence",
  },
  phase_4_extraction: { short: "Extraction", long: "Data extraction", milestone: "evidence" },
  phase_4_pdf_vision_table_extraction: {
    short: "Table extraction",
    long: "PDF table extraction (vision)",
    milestone: "evidence",
  },
  quality_rob2: { short: "RoB 2", long: "Risk of bias (RoB 2)", milestone: "evidence" },
  quality_robins_i: { short: "ROBINS-I", long: "Risk of bias (ROBINS-I)", milestone: "evidence" },
  quality_casp: { short: "CASP", long: "Quality appraisal (CASP)", milestone: "evidence" },
  quality_mmat: { short: "MMAT", long: "Quality appraisal (MMAT)", milestone: "evidence" },
  phase_4b_embedding: { short: "Embedding", long: "Evidence indexing (embeddings)", milestone: "evidence" },
  phase_5_synthesis: { short: "Synthesis", long: "Evidence synthesis", milestone: "synthesis" },
  phase_5_narrative_direction: { short: "Narrative", long: "Narrative direction", milestone: "synthesis" },
  phase_5b_knowledge_graph: { short: "Knowledge graph", long: "Knowledge graph", milestone: "synthesis" },
  phase_5c_pre_writing_gate: {
    short: "Pre-writing check",
    long: "Pre-writing readiness check",
    milestone: "synthesis",
  },
  phase_6_writing: { short: "Writing", long: "Manuscript writing", milestone: "manuscript" },
  phase_6a_hyde: { short: "Query drafting", long: "Retrieval query drafting (HyDE)", milestone: "manuscript" },
  phase_6_hyde: { short: "Query drafting", long: "Retrieval query drafting (HyDE)", milestone: "manuscript" },
  phase_6a2_outline: { short: "Outline", long: "Section outlines", milestone: "manuscript" },
  phase_6_writing_outline: { short: "Outline", long: "Section outlines", milestone: "manuscript" },
  phase_6_rerank: { short: "Reranking", long: "Evidence reranking", milestone: "manuscript" },
  phase_6b_phase_a: { short: "Core sections", long: "Drafting Abstract to Results", milestone: "manuscript" },
  phase_6c_phase_b: {
    short: "Discussion",
    long: "Drafting Discussion and Conclusion",
    milestone: "manuscript",
  },
  writing_contradiction_resolver: {
    short: "Contradictions",
    long: "Contradiction check",
    milestone: "manuscript",
  },
  phase_6d_assembly: { short: "Assembly", long: "Manuscript assembly", milestone: "manuscript" },
  phase_6e_concepts: { short: "Concept diagrams", long: "Concept diagrams", milestone: "manuscript" },
  phase_6e_concept_diagram: { short: "Concept diagrams", long: "Concept diagrams", milestone: "manuscript" },
  phase_6f_custom_diagrams: { short: "Custom diagrams", long: "Custom diagrams", milestone: "manuscript" },
  phase_6f_custom_diagram_preparer: {
    short: "Diagram planning",
    long: "Custom diagrams: planning",
    milestone: "manuscript",
  },
  phase_6f_custom_diagram_drawing: {
    short: "Diagram drawing",
    long: "Custom diagrams: drawing",
    milestone: "manuscript",
  },
  phase_6f_custom_diagram_critic: {
    short: "Diagram review",
    long: "Custom diagrams: review",
    milestone: "manuscript",
  },
  phase_6f_custom_diagram_placement: {
    short: "Diagram placement",
    long: "Custom diagrams: placement",
    milestone: "manuscript",
  },
  phase_6_humanizer: { short: "Humanizer", long: "Humanizer pass", milestone: "manuscript" },
  phase_7_audit: { short: "Audit", long: "Manuscript audit", milestone: "finalize" },
  finalize: { short: "Finalize", long: "Finalize and export", milestone: "finalize" },
} as const satisfies Record<string, PhaseMeta>

export type PhaseId = keyof typeof PHASE_META_TABLE

export const PHASE_META: Readonly<Record<PhaseId, PhaseMeta>> = PHASE_META_TABLE

export const PHASE_IDS = Object.keys(PHASE_META) as PhaseId[]

function labelMap(form: "short" | "long"): Record<string, string> {
  return Object.fromEntries(PHASE_IDS.map((id) => [id, PHASE_META[id][form]]))
}

/** Long phase labels keyed by phase id. Derived from PHASE_META. */
export const PHASE_LABELS: Record<string, string> = labelMap("long")

/** Short phase labels keyed by phase id. Derived from PHASE_META. */
export const PHASE_SHORT_LABELS: Record<string, string> = labelMap("short")

export function isPhaseId(value: string): value is PhaseId {
  return Object.prototype.hasOwnProperty.call(PHASE_META, value)
}

function normalizePhaseKey(raw: string): string {
  return raw
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .toLowerCase()
    .replace(/[\s\-./]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "")
}

const PHASE_IDS_BY_LENGTH = [...PHASE_IDS].sort((a, b) => b.length - a.length)

/** Resolve a phase id, raw backend phase string, or cost-record key to a known PhaseId. */
export function resolvePhaseId(raw: string | null | undefined): PhaseId | null {
  if (!raw) return null
  if (isPhaseId(raw)) return raw
  const key = normalizePhaseKey(raw)
  if (isPhaseId(key)) return key
  return PHASE_IDS_BY_LENGTH.find((id) => key.startsWith(`${id}_`)) ?? null
}

const PHASE_NUMBER_MILESTONE: Record<string, MilestoneId> = {
  "1": "prospero",
  "2": "discovery",
  "3": "discovery",
  "4": "evidence",
  "5": "synthesis",
  "6": "manuscript",
  "7": "finalize",
}

function milestoneIdForPhase(phase: string): MilestoneId | null {
  const id = resolvePhaseId(phase)
  if (id) return PHASE_META[id].milestone
  const match = /^phase_(\d+)/.exec(normalizePhaseKey(phase))
  return match ? (PHASE_NUMBER_MILESTONE[match[1]] ?? null) : null
}

function sentenceCaseSnake(value: string): string {
  const words = value.split("_").filter(Boolean).join(" ")
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : ""
}

/**
 * Human label for a phase id or raw backend phase string.
 * Unknown keys drop the `phase_<n><x>_` / `quality_` prefix and are sentence-cased.
 */
export function phaseLabel(idOrRaw: string, form: "short" | "long" = "long"): string {
  const id = resolvePhaseId(idOrRaw)
  if (id) return PHASE_META[id][form]
  const key = normalizePhaseKey(idOrRaw)
  const stripped = key.replace(/^phase_\d+[a-z]?\d*_/, "").replace(/^quality_/, "")
  return sentenceCaseSnake(stripped || key) || idOrRaw
}

/** Interleaved phases that belong to a parent milestone but are not in PHASE_MILESTONES[].phases. */
export const INTERLEAVED_PHASE_MILESTONE: Record<string, PhaseMilestoneKey> = Object.fromEntries(
  PHASE_IDS.filter(
    (id) => !PHASE_MILESTONES.some((milestone) => (milestone.phases as readonly string[]).includes(id)),
  ).map((id) => [id, PHASE_META[id].milestone]),
)

export function milestoneForPhase(phase: string): PhaseMilestone | null {
  const direct = PHASE_MILESTONES.find((milestone) =>
    milestone.phases.some((milestonePhase) => milestonePhase === phase),
  )
  if (direct) return direct
  const milestoneKey = milestoneIdForPhase(phase)
  if (!milestoneKey) return null
  return PHASE_MILESTONES.find((milestone) => milestone.key === milestoneKey) ?? null
}

/**
 * Every known phase in a milestone: its timeline phases first, then its sub-phases.
 * Alias ids with identical labels collapse to the first (canonical checkpoint) id.
 */
export function phasesInMilestone(milestoneId: MilestoneId): PhaseId[] {
  const milestone = PHASE_MILESTONES.find((m) => m.key === milestoneId)
  if (!milestone) return []
  const primary = milestone.phases as readonly PhaseId[]
  const rest = PHASE_IDS.filter((id) => PHASE_META[id].milestone === milestoneId && !primary.includes(id))
  const seen = new Set<string>()
  return [...primary, ...rest].filter((id) => {
    const key = `${PHASE_META[id].short}|${PHASE_META[id].long}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

export function milestoneLabelForPhase(phase: string): string {
  return milestoneForPhase(phase)?.label ?? PHASE_LABELS[phase] ?? phase
}

/** Phase order for resume-from-phase (matches backend USER_RESUMABLE_PHASE_ORDER). */
export const RESUME_PHASE_ORDER = [
  "phase_1_prospero_gate",
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
  | "awaiting_review"
  | "needs_revision"
  | "awaiting_prospero"
  | "config_generating"
  | "config_ready"

export const STATUS_LABEL: Record<RunStatus, string> = {
  idle: "Ready",
  connecting: "Connecting",
  streaming: "Running",
  done: "Completed",
  error: "Failed",
  cancelled: "Cancelled",
  stale: "Stale",
  awaiting_review: "Awaiting review",
  needs_revision: "Needs revision",
  awaiting_prospero: "PROSPERO pending",
  config_generating: "Generating config",
  config_ready: "Config ready",
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
  awaiting_review: "warning",
  needs_revision: "warning",
  awaiting_prospero: "warning",
  config_generating: "active",
  config_ready: "warning",
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
  awaiting_review: "bg-intent-warning",
  needs_revision: "bg-intent-warning",
  awaiting_prospero: "bg-intent-warning",
  config_generating: "bg-intent-active",
  config_ready: "bg-intent-warning",
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
  awaiting_review: "text-intent-warning",
  needs_revision: "text-intent-warning",
  awaiting_prospero: "text-intent-warning",
  config_generating: "text-intent-active",
  config_ready: "text-intent-warning",
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
  awaiting_review: "bg-intent-warning/60",
  needs_revision: "bg-intent-warning",
  awaiting_prospero: "bg-intent-warning/60",
  config_generating: "bg-intent-active",
  config_ready: "bg-intent-warning/60",
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
  isAwaitingProspero?: boolean
  isNeedsRevision?: boolean
}

/** Client-side PROSPERO registration number format (CRD + 9+ digits). */
export function isProsperoRegistrationNumberValid(value: string): boolean {
  return /^CRD\d{9,}$/i.test(value.trim())
}

/** Run info strip label + text class (canonical status presentation). */
export function resolveRunHeaderStatus(input: RunHeaderStatusInput): {
  label: string
  className: string
} {
  const {
    status,
    isDone,
    isRunning,
    isCancelled,
    isFailed,
    isAwaitingReview,
    isAwaitingProspero,
    isNeedsRevision,
  } = input
  const resolved = resolveRunStatus(status)
  if (isAwaitingProspero && !isDone) {
    const key = resolved === "config_generating" || resolved === "config_ready" ? resolved : "awaiting_prospero"
    return { label: STATUS_LABEL[key], className: STATUS_TEXT[key] }
  }
  if (isAwaitingReview && !isDone) {
    return { label: STATUS_LABEL.awaiting_review, className: STATUS_TEXT.awaiting_review }
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
  if (isNeedsRevision) {
    return { label: STATUS_LABEL.needs_revision, className: STATUS_TEXT.needs_revision }
  }
  if (status === "done" || isDone) {
    return { label: STATUS_LABEL.done, className: STATUS_TEXT.done }
  }
  return { label: runStatusLabel(status), className: STATUS_TEXT[resolved] }
}

/**
 * Display label for any raw run status. Known aliases go through resolveRunStatus;
 * unrecognised non-empty values are sentence-cased instead of collapsing to "Ready".
 */
export function runStatusLabel(raw: string | null | undefined): string {
  const resolved = resolveRunStatus(raw)
  const normalized = (raw ?? "").trim().toLowerCase()
  if (resolved === "idle" && normalized && normalized !== "idle") {
    return sentenceCaseSnake(normalizePhaseKey(normalized))
  }
  return STATUS_LABEL[resolved]
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
  phase_1_prospero_gate: "--color-phase-1-prospero-gate",
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

/** Short phase labels (alias of PHASE_SHORT_LABELS, kept for existing callers). */
export const PHASE_LABEL_MAP: Record<string, string> = PHASE_SHORT_LABELS

// ---------------------------------------------------------------------------

/** True when a history row is parked before PROSPERO registration. */
export function isProsperoPendingStatus(raw: string | null | undefined): boolean {
  const normalized = (raw ?? "").toLowerCase()
  return normalized === "awaiting_prospero"
    || normalized === "config_generating"
    || normalized === "config_ready"
}

/** True when a history row is parked for human screening review. */
export function isReviewPendingStatus(raw: string | null | undefined): boolean {
  return (raw ?? "").toLowerCase() === "awaiting_review"
}

/** True when finalize completed but the manuscript/audit gate asked for revisions. */
export function isNeedsRevisionStatus(raw: string | null | undefined): boolean {
  const normalized = (raw ?? "").toLowerCase()
  return normalized === "needs_revision" || normalized === "needs-revision"
}

export const NEEDS_REVISION_EXPLANATION =
  "The run finished, but the manuscript audit gate flagged issues that need revision. Results are available; open Results > Quality to see the audit findings."

/** True when a run is parked at an external human gate (not actively streaming). */
export function isParkedGateStatus(raw: string | null | undefined): boolean {
  return isProsperoPendingStatus(raw) || isReviewPendingStatus(raw)
}

export function isConfigDraftStatus(raw: string | null | undefined): boolean {
  const normalized = (raw ?? "").toLowerCase()
  return normalized === "config_generating" || normalized === "config_ready"
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
  if (s === "awaiting_review") return "awaiting_review"
  if (s === "needs_revision" || s === "needs-revision") return "needs_revision"
  if (s === "awaiting_prospero") return "awaiting_prospero"
  if (s === "config_generating") return "config_generating"
  if (s === "config_ready") return "config_ready"
  return "idle"
}
