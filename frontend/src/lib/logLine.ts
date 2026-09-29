import type { ReviewEvent } from "@/lib/api"
import { PHASE_LABELS, humanizeReason, phaseLabel } from "@/lib/constants"
import { formatCompact } from "@/lib/format"
import { decodeHtmlEntities, humanizeIdentifier, humanizeSnake, shortModelName } from "@/lib/humanize"

// ---------------------------------------------------------------------------
// Timestamp helpers
// ---------------------------------------------------------------------------

/**
 * Convert a UTC ISO-8601 timestamp (as emitted by the backend) to a local
 * HH:MM:SS string in the browser's timezone.  Falls back to raw UTC slice if
 * parsing fails.
 */
export function fmtTs(ts: string | null | undefined): string {
  if (!ts) return "--:--:--"
  try {
    const raw = String(ts).trim()
    const normalized = (() => {
      if (!raw) return raw
      const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/.test(raw)
      if (hasTimezone) return raw
      // Normalize common backend variants that omit timezone and should be UTC.
      // Example: "2026-03-10T08:14:29.123456" -> "...Z"
      if (/^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}/.test(raw)) {
        return raw.replace(" ", "T") + "Z"
      }
      return raw
    })()
    return new Date(normalized).toLocaleTimeString("en-US", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    })
  } catch {
    const m = String(ts).match(/(\d{2}:\d{2}:\d{2})/)
    return m?.[1] ?? "--:--:--"
  }
}

// ---------------------------------------------------------------------------
// Level type
// ---------------------------------------------------------------------------

export type LogLevel = "info" | "warn" | "error" | "dim" | "include" | "exclude" | "exclude-heuristic" | "status"

function eventTs(ev: ReviewEvent): string | undefined {
  return "ts" in ev ? ev.ts : undefined
}

export type LogSeverity = "info" | "warn" | "error" | "decision" | "progress" | "status" | "dim"

export type LogRowKind =
  | "phase"
  | "done"
  | "progress"
  | "status"
  | "llm"
  | "search"
  | "decision"
  | "pdf"
  | "extract"
  | "synth"
  | "ratelimit"
  | "db"
  | "funnel"
  | "batch"
  | "other"

export interface LogRenderEntry {
  /** Full searchable line: `[HH:MM:SS] TAG message`. */
  text: string
  /** Local HH:MM:SS, or "" when the event has no timestamp. */
  ts: string
  /** Raw tag (see LOG_TAG_GLOSSARY); humanize with humanizeLogTag for display. */
  tag: string
  /** Secondary tag, e.g. `AUTO` for rule-based screening decisions. */
  subTag?: string
  /** Human-readable message shown in the row. */
  message: string
  /** Full detail shown when the row is expanded (untruncated reason, full model path). */
  detail?: string
  level: LogLevel
  severity: LogSeverity
  kind: LogRowKind
  phase?: string
  eventType: ReviewEvent["type"]
  compactable: boolean
  groupKey?: string
  isResumeRelated: boolean
  isResumeNoOp: boolean
}

function topReasonSummary(reasonBreakdown: Record<string, number>, topN = 3): string {
  const entries = Object.entries(reasonBreakdown)
    .filter(([, count]) => Number(count) > 0)
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, topN)
  if (entries.length === 0) return ""
  return entries.map(([code, count]) => `${code}=${count}`).join(", ")
}

function normalizeDoiText(text: string): string {
  return text.replace(/https?:\/\/doi\.org\/https?:\/\/doi\.org\//gi, "https://doi.org/")
}

function asPercentLabel(threshold: number | null | undefined): string {
  if (threshold == null) return "35%"
  if (threshold > 1) return `${Math.round(threshold)}%`
  return `${Math.round(threshold * 100)}%`
}

const REASON_MAX_CHARS = 95

export function truncateWithEllipsis(text: string, max: number): string {
  if (text.length <= max) return text
  return `${text.slice(0, max - 1).trimEnd()}…`
}

// ---------------------------------------------------------------------------
// API-call rows
// ---------------------------------------------------------------------------

type ApiCallEvent = Extract<ReviewEvent, { type: "api_call" }>

function isSuccessStatus(status: string | null | undefined): boolean {
  const s = (status ?? "").trim().toLowerCase()
  return s === "" || s === "success" || s === "ok"
}

/** 8401 -> "8.4s", 120 -> "120ms". */
export function formatLatency(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function formatCallCost(usd: number): string {
  return `$${usd.toFixed(usd >= 1 ? 2 : 4)}`
}

function callTypeLabel(source: string, callType: string): string | null {
  const stripped = callType.replace(/^llm_/i, "")
  if (!stripped || stripped.toLowerCase() === source.toLowerCase()) return null
  const label = humanizeIdentifier(stripped)
  return /^[A-Z]{2,}/.test(label) ? label : label.toLowerCase()
}

/** `Writing · outline · deepseek-v4-pro · 8.4s · 10.3K in / 1.1K out · $0.0179`, prefixed with the status on failure. */
export function formatApiCallMessage(ev: ApiCallEvent): string {
  const source = ev.source ?? ""
  const parts: string[] = []
  if (!isSuccessStatus(ev.status)) parts.push(humanizeSnake(ev.status))
  if (source) parts.push(humanizeIdentifier(source))
  const callType = ev.call_type ? callTypeLabel(source, ev.call_type) : null
  if (callType) parts.push(callType)
  const model = ev.model ? shortModelName(ev.model).name : ""
  if (model) parts.push(model)
  if (ev.section_name) parts.push(`${humanizeSnake(ev.section_name).toLowerCase()} section`)
  if (ev.latency_ms != null) parts.push(formatLatency(ev.latency_ms))
  if (ev.tokens_in != null && ev.tokens_in > 0) {
    parts.push(`${formatCompact(ev.tokens_in)} in / ${formatCompact(ev.tokens_out ?? 0)} out`)
  }
  if (ev.cost_usd != null && ev.cost_usd > 0) parts.push(formatCallCost(ev.cost_usd))
  return parts.join(" · ")
}

function apiCallRawTokens(ev: ApiCallEvent): string {
  return [
    ev.status,
    ev.source,
    ev.call_type,
    ev.model,
    ev.section_name,
    ev.latency_ms != null ? `${ev.latency_ms}ms` : null,
  ]
    .filter(Boolean)
    .join(" | ")
}

// ---------------------------------------------------------------------------
// Event -> log line conversion
// ---------------------------------------------------------------------------

export function eventToLogEntry(ev: ReviewEvent): LogRenderEntry {
  const finalize = (
    data: Omit<LogRenderEntry, "eventType" | "text" | "ts"> & {
      tsRaw: string | null | undefined
      /** Extra raw tokens appended to `text` so search matches backend ids. */
      searchText?: string
    },
  ): LogRenderEntry => {
    const { tsRaw, searchText, ...rest } = data
    const ts = tsRaw ? fmtTs(tsRaw) : ""
    const message = normalizeDoiText(rest.message)
    const tagText = rest.subTag ? `${rest.tag} [${rest.subTag}]` : rest.tag
    return {
      ...rest,
      ts,
      message,
      detail: rest.detail ? normalizeDoiText(rest.detail) : undefined,
      text: `[${ts || "--:--:--"}] ${tagText} ${message}${searchText ? ` ${searchText}` : ""}`,
      eventType: ev.type,
    }
  }

  switch (ev.type) {
    case "phase_start": {
      const label = PHASE_LABELS[ev.phase as string] ?? ev.phase
      return finalize({
        tsRaw: ev.ts,
        tag: "PHASE",
        message: `${label}${ev.description ? "  " + ev.description : ""}`,
        level: "info",
        severity: "info",
        kind: "phase",
        phase: ev.phase,
        compactable: false,
        groupKey: `phase:${ev.phase}`,
        isResumeRelated: false,
        isResumeNoOp: false,
      })
    }

    case "phase_done": {
      const s = ev.summary as Record<string, unknown> | null | undefined
      let detail = ""
      if (ev.phase === "fulltext_pdf_retrieval") {
        const attempted = Number(s?.attempted ?? 0)
        const retrieved = Number(s?.retrieved ?? 0)
        const unavailable = Number(s?.unavailable ?? Math.max(attempted - retrieved, 0))
        const reasons = (s?.reason_breakdown as Record<string, number> | undefined) ?? {}
        const reasonText = topReasonSummary(reasons)
        detail = `  attempted=${attempted}, retrieved=${retrieved}, unavailable=${unavailable}`
        if (reasonText) detail += ` (${reasonText})`
      } else if (s?.included != null && s?.screened != null) {
        const kappaStr = s?.kappa != null ? `  kappa=${Number(s.kappa).toFixed(2)}` : ""
        const excluded = s?.excluded != null ? `  excluded=${s.excluded}` : ""
        const reasons = (s?.reason_breakdown as Record<string, number> | undefined) ?? {}
        const reasonText = topReasonSummary(reasons)
        detail = `  ${s.included} included of ${s.screened} papers${excluded}${kappaStr}`
        if (reasonText) detail += `  top reasons: ${reasonText}`
      }
      else if (s?.new_papers != null)
        detail = `  ${Number(s.new_papers) > 0 ? s.new_papers + " new papers found" : "no new papers"}`
      else if (s?.fetched != null)
        detail = `  ${s.fetched} papers`
      else if (s?.records != null)
        detail = `  ${s.records} records`
      else if (s?.papers != null)
        detail = `  ${s.papers} papers`
      const label = PHASE_LABELS[ev.phase as string] ?? ev.phase
      return finalize({
        tsRaw: ev.ts,
        tag: "DONE",
        message: `${label}${detail}`,
        level: "info",
        severity: "info",
        kind: "done",
        phase: ev.phase,
        compactable: false,
        groupKey: `done:${ev.phase}`,
        isResumeRelated: false,
        isResumeNoOp: false,
      })
    }

    case "progress":
      return finalize({
        tsRaw: ev.ts,
        tag: "PROG",
        message: `${phaseLabel(ev.phase, "short")}: ${ev.current}/${ev.total}`,
        level: "dim",
        severity: "progress",
        kind: "progress",
        phase: ev.phase,
        compactable: true,
        groupKey: `progress:${ev.phase}`,
        isResumeRelated: false,
        isResumeNoOp: false,
      })

    case "status": {
      const msg = ev.message ?? ""
      const isTimer = msg.includes("done in") || msg.includes("elapsed") || msg.includes("starting (")
      const resumeMessage = msg.trim().toLowerCase() === "resume"
      return finalize({
        tsRaw: ev.ts,
        tag: isTimer ? "TIMER" : "...",
        message: msg,
        level: isTimer ? "dim" : "status",
        severity: isTimer ? "dim" : "status",
        kind: "status",
        compactable: !isTimer,
        groupKey: isTimer ? "timer" : "status",
        isResumeRelated: resumeMessage,
        isResumeNoOp: resumeMessage,
      })
    }

    case "warn":
      return finalize({
        tsRaw: ev.ts,
        tag: "WARN",
        message: ev.message ?? "",
        level: "warn",
        severity: "warn",
        kind: "status",
        compactable: false,
        groupKey: "warn",
        isResumeRelated: false,
        isResumeNoOp: false,
      })

    case "screening_calibration": {
      const inc = Math.round(ev.include_threshold * 100)
      const exc = Math.round(ev.exclude_threshold * 100)
      return finalize({
        tsRaw: ev.ts,
        tag: "CALIB",
        message: `include >= ${inc}%  exclude <= ${exc}%  kappa ${ev.kappa.toFixed(2)}  sample ${ev.sample_size}`,
        level: "info",
        severity: "info",
        kind: "status",
        phase: "screening_calibration",
        compactable: false,
        groupKey: "calibration",
        isResumeRelated: false,
        isResumeNoOp: false,
      })
    }

    case "api_call": {
      const ok = isSuccessStatus(ev.status)
      return finalize({
        tsRaw: ev.ts,
        tag: "LLM",
        message: formatApiCallMessage(ev),
        searchText: apiCallRawTokens(ev),
        detail: ev.model ? `Model: ${ev.model}` : undefined,
        level: ok ? "dim" : "error",
        severity: ok ? "dim" : "error",
        kind: "llm",
        phase: ev.phase,
        compactable: false,
        groupKey: `llm:${ev.phase}:${ev.call_type}`,
        isResumeRelated: false,
        isResumeNoOp: false,
      })
    }

    case "connector_result": {
      const queryStr = ev.query ? `  |  query: ${ev.query}` : ""
      return finalize({
        tsRaw: ev.ts,
        tag: "SEARCH",
        message: `${ev.status === "success" ? "OK" : "FAIL"} ${ev.name}: ${ev.status === "success" ? ev.records + " records" : (ev.error ?? "unknown error")}${queryStr}`,
        level: ev.status === "success" ? "info" : "warn",
        severity: ev.status === "success" ? "info" : "warn",
        kind: "search",
        phase: "phase_2_search",
        compactable: false,
        groupKey: `search:${ev.name}`,
        isResumeRelated: false,
        isResumeNoOp: false,
      })
    }

    case "screening_decision": {
      const conf = ev.confidence != null ? ` ${Math.round(ev.confidence * 100)}%` : ""
      const label = decodeHtmlEntities(ev.title ?? ev.paper_id?.slice(0, 32) ?? "")
      const rawReason = ev.reason ?? ev.reason_code ?? ""
      // Support extended reasons like "insufficient_content_heuristic|3w" that encode
      // the abstract word count after a pipe delimiter for auditability.
      const pipeIdx = rawReason.indexOf("|")
      const baseReason = pipeIdx >= 0 ? rawReason.slice(0, pipeIdx) : rawReason
      const wcSuffix = pipeIdx >= 0 ? ` (${rawReason.slice(pipeIdx + 1)})` : ""
      const fullReason = rawReason
        ? decodeHtmlEntities((ev.reason_label ?? humanizeReason(baseReason)) + wcSuffix)
        : ""
      const displayReason = truncateWithEllipsis(fullReason, REASON_MAX_CHARS)
      const reasonText = displayReason ? `  -- ${displayReason}` : ""
      return finalize({
        tsRaw: ev.ts,
        tag: ev.decision === "include" ? "INCLUDE" : "EXCLUDE",
        subTag: ev.method === "heuristic" ? "AUTO" : "LLM",
        message: `${label}${conf}${reasonText}`,
        detail: displayReason !== fullReason ? `Reason: ${fullReason}` : undefined,
        level: ev.decision === "include" ? "include" : ev.method === "heuristic" ? "exclude-heuristic" : "exclude",
        severity: "decision",
        kind: "decision",
        phase: "phase_3_screening",
        compactable: false,
        groupKey: `decision:${ev.decision}:${ev.method ?? "llm"}`,
        isResumeRelated: false,
        isResumeNoOp: false,
      })
    }

    case "pdf_result": {
      const tier = ev.source && ev.source !== "abstract" ? ev.source : "no-pdf"
      const title = decodeHtmlEntities(ev.title)
      const label = title ? truncateWithEllipsis(title, 60) : ev.paper_id?.slice(0, 16) ?? ""
      const reasonText = ev.reason_label ?? humanizeReason(ev.reason_code)
      return finalize({
        tsRaw: ev.ts,
        tag: "PDF",
        message: `${ev.success ? "OK" : "FAIL"}  ${label}  (${tier}) -- ${reasonText}`,
        detail: title && label !== title ? `Title: ${title}` : undefined,
        level: ev.success ? "dim" : "warn",
        severity: ev.success ? "dim" : "warn",
        kind: "pdf",
        phase: "fulltext_pdf_retrieval",
        compactable: false,
        groupKey: `pdf:${ev.success ? "ok" : "fail"}:${tier}`,
        isResumeRelated: false,
        isResumeNoOp: false,
      })
    }

    case "extraction_paper":
      return finalize({
        tsRaw: ev.ts,
        tag: "EXTRACT",
        message: `${ev.paper_id?.slice(0, 16) ?? ""}  design: ${humanizeSnake(ev.design)}  risk of bias: ${humanizeSnake(ev.rob_judgment)}`,
        level: "dim",
        severity: "dim",
        kind: "extract",
        phase: "phase_4_extraction_quality",
        compactable: false,
        groupKey: `extract:${ev.design}`,
        isResumeRelated: false,
        isResumeNoOp: false,
      })

    case "synthesis":
      return finalize({
        tsRaw: ev.ts,
        tag: "SYNTH",
        message: `${ev.feasible ? "pooling feasible" : "pooling not feasible"}  groups ${ev.groups}  studies ${ev.n_studies}`,
        level: "info",
        severity: "info",
        kind: "synth",
        phase: "phase_5_synthesis",
        compactable: false,
        groupKey: "synthesis",
        isResumeRelated: false,
        isResumeNoOp: false,
      })

    case "search_override_status": {
      const badge = ev.status === "applied" ? "applied" : ev.status === "miss" ? "missed" : "absent"
      const lvl: LogLevel = ev.status === "applied" ? "info" : "warn"
      return finalize({
        tsRaw: ev.ts,
        tag: "SRCHOV",
        message: `${ev.database}: ${badge} -- ${ev.detail}`,
        level: lvl,
        severity: lvl === "warn" ? "warn" : "info",
        kind: "search",
        phase: "phase_2_search",
        compactable: false,
        groupKey: `search-override:${ev.database}`,
        isResumeRelated: false,
        isResumeNoOp: false,
      })
    }

    case "rate_limit_wait": {
      const waitedStr = ev.waited_seconds != null ? ` (${ev.waited_seconds.toFixed(1)}s)` : ""
      return finalize({
        tsRaw: ev.ts,
        tag: "RATELIMIT",
        message: `${ev.tier}: ${ev.slots_used}/${ev.limit} slots -- waiting${waitedStr}`,
        level: "warn",
        severity: "warn",
        kind: "ratelimit",
        compactable: false,
        groupKey: `ratelimit:${ev.tier}`,
        isResumeRelated: false,
        isResumeNoOp: false,
      })
    }

    case "rate_limit_resolved":
      return finalize({
        tsRaw: ev.ts,
        tag: "RATELIMIT",
        message: `${ev.tier}: cleared after ${ev.waited_seconds.toFixed(1)}s`,
        level: "info",
        severity: "info",
        kind: "ratelimit",
        compactable: false,
        groupKey: `ratelimit:${ev.tier}`,
        isResumeRelated: false,
        isResumeNoOp: false,
      })

    case "db_ready":
      return finalize({
        tsRaw: ev.ts,
        tag: "DB",
        message: "Ready. Database explorer unlocked.",
        level: "dim",
        severity: "dim",
        kind: "db",
        compactable: false,
        groupKey: "db-ready",
        isResumeRelated: false,
        isResumeNoOp: false,
      })

    case "done": {
      const outputStatus = String(ev.outputs?.status ?? "").toLowerCase()
      const doneText =
        outputStatus === "awaiting_prospero"
          ? "Paused at PROSPERO gate. Enter registration on the Config tab to continue."
          : outputStatus === "awaiting_review"
            ? "Paused for human screening review."
            : "Review complete"
      return finalize({
        tsRaw: eventTs(ev),
        tag: "DONE",
        message: doneText,
        level: "info",
        severity: "info",
        kind: "done",
        compactable: false,
        groupKey: `done:${outputStatus || "review"}`,
        isResumeRelated: false,
        isResumeNoOp: false,
      })
    }

    case "error":
      return finalize({
        tsRaw: eventTs(ev),
        tag: "ERROR",
        message: ev.msg,
        level: "error",
        severity: "error",
        kind: "other",
        compactable: false,
        groupKey: "error",
        isResumeRelated: false,
        isResumeNoOp: false,
      })

    case "cancelled":
      return finalize({
        tsRaw: eventTs(ev),
        tag: "CANCEL",
        message: "Review cancelled.",
        level: "warn",
        severity: "warn",
        kind: "other",
        compactable: false,
        groupKey: "cancelled",
        isResumeRelated: false,
        isResumeNoOp: false,
      })

    case "screening_prefilter_done": {
      const pf = ev as unknown as Record<string, number>
      const deduped = pf.deduped ?? 0
      const metaRej = pf.metadata_rejected ?? 0
      const afterMetadata = pf.after_metadata ?? (deduped - metaRej)
      const autoExcl = pf.automation_excluded ?? 0
      const toLlm = pf.to_llm ?? 0
      const cap = typeof pf.dual_review_cap === "number" ? pf.dual_review_cap : null
      const emptyRescued = pf.empty_abstract_rescued ?? 0
      const reasons = ((ev as unknown as { reason_breakdown?: Record<string, number> }).reason_breakdown) ?? {}
      const reasonText = topReasonSummary(reasons)
      const capText = cap !== null ? `, cap ${cap}` : ""
      const rescueText = emptyRescued > 0 ? `, ${emptyRescued} empty-abstract rescues` : ""
      return finalize({
        tsRaw: ev.ts,
        tag: "FUNNEL",
        message: `${deduped} deduped -> ${afterMetadata} after metadata -> ${toLlm} to AI review (${autoExcl} auto-excluded${capText}${rescueText})${reasonText ? ` [${reasonText}]` : ""}`,
        level: "info",
        severity: "info",
        kind: "funnel",
        phase: "phase_3_screening",
        compactable: false,
        groupKey: "funnel:prefilter",
        isResumeRelated: false,
        isResumeNoOp: false,
      })
    }

    case "deterministic_exclusion_qa_sample": {
      const qa = ev as unknown as Record<string, number>
      const sample = qa.sample_size ?? 0
      const pool = qa.pool_size ?? 0
      return finalize({
        tsRaw: ev.ts,
        tag: "QA",
        message: `Rule-based exclusion sample prepared: ${sample}/${pool} records for manual review`,
        level: "status",
        severity: "status",
        kind: "status",
        phase: "phase_3_screening",
        compactable: false,
        groupKey: "qa:deterministic-exclude",
        isResumeRelated: false,
        isResumeNoOp: false,
      })
    }

    case "batch_screen_done": {
      const bs = ev as unknown as Record<string, number>
      const scored = bs.scored ?? 0
      const forwarded = bs.forwarded ?? 0
      const excluded = bs.excluded ?? 0
      const thresholdLabel = asPercentLabel(typeof bs.threshold === "number" ? bs.threshold : null)
      const skipNote = bs.skipped_resume ? ` (${bs.skipped_resume} skipped on resume)` : ""
      return finalize({
        tsRaw: ev.ts,
        tag: "BATCH",
        message: `${scored} ranked -> ${forwarded} to dual review, ${excluded} auto-excluded (score < ${thresholdLabel})${skipNote}`,
        level: "info",
        severity: "info",
        kind: "batch",
        phase: "phase_3_screening",
        compactable: false,
        groupKey: "batch:screen",
        isResumeRelated: bs.skipped_resume > 0,
        isResumeNoOp: scored === 0 && forwarded === 0 && excluded === 0 && bs.skipped_resume > 0,
      })
    }

    case "screening_cap_overflow": {
      const ov = ev as unknown as Record<string, number>
      const rate = typeof ov.validation_tail_forward_rate === "number" ? `${(ov.validation_tail_forward_rate * 100).toFixed(1)}%` : "--"
      const trigger = typeof ov.trigger_threshold === "number" ? `${(ov.trigger_threshold * 100).toFixed(1)}%` : "--"
      return finalize({
        tsRaw: ev.ts,
        tag: "CAP",
        message: `Tail yield ${rate} (trigger ${trigger}) -> +${ov.overflow_forwarded ?? 0} forwarded from ${ov.overflow_evaluated ?? 0} overflow candidates`,
        level: "status",
        severity: "status",
        kind: "status",
        phase: "phase_3_screening",
        compactable: false,
        groupKey: "cap:overflow",
        isResumeRelated: false,
        isResumeNoOp: false,
      })
    }

    default:
      return finalize({
        tsRaw: eventTs(ev),
        tag: "...",
        message: humanizeSnake(ev.type),
        level: "dim",
        severity: "dim",
        kind: "other",
        compactable: false,
        groupKey: `other:${ev.type}`,
        isResumeRelated: false,
        isResumeNoOp: false,
      })
  }
}

export function eventToLogLine(ev: ReviewEvent): { text: string; level: LogLevel } {
  const entry = eventToLogEntry(ev)
  return { text: entry.text, level: entry.level }
}

export type LogSeverityFilter = "all" | "warnings" | "errors" | "decisions"

export const LOG_SEVERITY_FILTERS: { id: LogSeverityFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "warnings", label: "Warnings & errors" },
  { id: "errors", label: "Errors" },
  { id: "decisions", label: "Decisions" },
]

export function matchesSeverityFilter(severity: LogSeverity, filter: LogSeverityFilter): boolean {
  switch (filter) {
    case "all":
      return true
    case "warnings":
      return severity === "warn" || severity === "error"
    case "errors":
      return severity === "error"
    case "decisions":
      return severity === "decision"
  }
}

/** Keeps phase_start events so filtered rows still group under the right phase header. */
export function filterEventsBySeverity(events: ReviewEvent[], filter: LogSeverityFilter): ReviewEvent[] {
  if (filter === "all") return events
  return events.filter(
    (ev) => ev.type === "phase_start" || matchesSeverityFilter(eventToLogEntry(ev).severity, filter),
  )
}
