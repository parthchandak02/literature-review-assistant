import type { ReviewEvent } from "@/lib/api"
import { PHASE_LABELS } from "@/lib/constants"

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
  text: string
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

function normalizeDoiText(text: string): string {
  return text.replace(/https?:\/\/doi\.org\/https?:\/\/doi\.org\//gi, "https://doi.org/")
}

function asPercentLabel(threshold: number | null | undefined): string {
  if (threshold == null) return "35%"
  if (threshold > 1) return `${Math.round(threshold)}%`
  return `${Math.round(threshold * 100)}%`
}

// ---------------------------------------------------------------------------
// Event -> log line conversion
// ---------------------------------------------------------------------------

export function eventToLogEntry(ev: ReviewEvent): LogRenderEntry {
  const finalize = (
    data: Omit<LogRenderEntry, "eventType">,
  ): LogRenderEntry => ({
    ...data,
    text: normalizeDoiText(data.text),
    eventType: ev.type,
  })

  switch (ev.type) {
    case "phase_start": {
      const label = PHASE_LABELS[ev.phase as string] ?? ev.phase
      return finalize({
        text: `[${fmtTs(ev.ts)}] PHASE  ${label}${ev.description ? "  " + ev.description : ""}`,
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
      if (s?.included != null && s?.screened != null) {
        const kappaStr = s?.kappa != null ? `  kappa=${Number(s.kappa).toFixed(2)}` : ""
        detail = `  ${s.included} included of ${s.screened} papers${kappaStr}`
      }
      else if (s?.new_papers != null)
        detail = `  ${Number(s.new_papers) > 0 ? s.new_papers + " new papers found" : "no new papers"}`
      else if (s?.fetched != null)
        detail = `  ${s.fetched} papers`
      else if (s?.records != null)
        detail = `  ${s.records} records`
      else if (s?.papers != null)
        detail = `  ${s.papers} papers`
      const phaseLabel = PHASE_LABELS[ev.phase as string] ?? ev.phase
      return finalize({
        text: `[${fmtTs(ev.ts)}] DONE   ${phaseLabel}${detail}`,
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
        text: `[${fmtTs(ev.ts)}] PROG   ${ev.phase}: ${ev.current}/${ev.total}`,
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
        text: `[${fmtTs(ev.ts)}] ${isTimer ? "TIMER  " : "...    "} ${msg}`,
        level: isTimer ? "dim" : "status",
        severity: isTimer ? "dim" : "status",
        kind: "status",
        compactable: !isTimer,
        groupKey: isTimer ? "timer" : "status",
        isResumeRelated: resumeMessage,
        isResumeNoOp: resumeMessage,
      })
    }

    case "screening_calibration": {
      const inc = Math.round(ev.include_threshold * 100)
      const exc = Math.round(ev.exclude_threshold * 100)
      return finalize({
        text: `[${fmtTs(ev.ts)}] CALIB  include>=${inc}%  exclude<=${exc}%  kappa=${ev.kappa.toFixed(2)}  n=${ev.sample_size}`,
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
      const tokStr =
        ev.tokens_in != null && ev.tokens_in > 0
          ? ` | ${ev.tokens_in}in/${ev.tokens_out ?? 0}out tok`
          : ""
      return finalize({
        text: `[${fmtTs(ev.ts)}] LLM    ${ev.status.toUpperCase().padEnd(7)} ${ev.source} | ${ev.call_type}${ev.model ? " | " + ev.model.split(":").pop() : ""}${ev.section_name ? " | section=" + ev.section_name : ""}${ev.latency_ms != null ? " | " + ev.latency_ms + "ms" : ""}${tokStr}${ev.cost_usd != null && ev.cost_usd > 0 ? " | $" + ev.cost_usd.toFixed(4) : ""}`,
        level: ev.status === "success" ? "dim" : "error",
        severity: ev.status === "success" ? "dim" : "error",
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
        text: `[${fmtTs(ev.ts)}] SEARCH ${ev.status === "success" ? "OK     " : "FAIL   "} ${ev.name}: ${ev.status === "success" ? ev.records + " records" : (ev.error ?? "unknown error")}${queryStr}`,
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
      const REASON_LABELS: Record<string, string> = {
        insufficient_content_heuristic: "auto-excluded: abstract absent or too short",
        protocol_only_heuristic: "auto-excluded: conference-only abstract",
        fulltext_no_pdf_heuristic: "auto-excluded: full-text PDF unavailable",
      }
      const conf = ev.confidence != null ? ` ${Math.round(ev.confidence * 100)}%` : ""
      const label = ev.title ?? ev.paper_id?.slice(0, 32) ?? ""
      const rawReason = ev.reason ?? ""
      // Support extended reasons like "insufficient_content_heuristic|3w" that encode
      // the abstract word count after a pipe delimiter for auditability.
      const pipeIdx = rawReason.indexOf("|")
      const baseReason = pipeIdx >= 0 ? rawReason.slice(0, pipeIdx) : rawReason
      const wcSuffix = pipeIdx >= 0 ? ` (${rawReason.slice(pipeIdx + 1)})` : ""
      const baseLabel = REASON_LABELS[baseReason] ?? rawReason
      const displayReason = rawReason ? (baseLabel + wcSuffix).slice(0, 95) : ""
      const reasonText = displayReason ? `  -- ${displayReason}` : ""
      const methodBadge = ev.method === "heuristic" ? "[AUTO]  " : "[LLM]   "
      const verb = ev.decision === "include" ? "INCLUDE" : "EXCLUDE"
      return finalize({
        text: `[${fmtTs(ev.ts)}] ${verb.padEnd(7)} ${methodBadge}${label}${conf}${reasonText}`,
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
      const label = ev.title ? ev.title.slice(0, 60) : ev.paper_id?.slice(0, 16) ?? ""
      return finalize({
        text: `[${fmtTs(ev.ts)}] PDF    ${ev.success ? "OK  " : "FAIL"}  ${label}  (${tier})`,
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
        text: `[${fmtTs(ev.ts)}] EXTRACT ${ev.paper_id?.slice(0, 16) ?? ""}  design=${ev.design}  rob=${ev.rob_judgment}`,
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
        text: `[${fmtTs(ev.ts)}] SYNTH  feasible=${ev.feasible}  groups=${ev.groups}  n=${ev.n_studies}`,
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
      const badge = ev.status === "applied" ? "APPLY " : ev.status === "miss" ? "MISS  " : "ABSENT"
      const lvl: LogLevel = ev.status === "applied" ? "info" : "warn"
      return finalize({
        text: `[${fmtTs(ev.ts)}] SRCHOV ${badge} ${ev.database}: ${ev.detail}`,
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
        text: `[${fmtTs(ev.ts)}] RATELIMIT  ${ev.tier}: ${ev.slots_used}/${ev.limit} slots -- waiting${waitedStr}`,
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
        text: `[${fmtTs(ev.ts)}] RATELIMIT  ${ev.tier}: cleared after ${ev.waited_seconds.toFixed(1)}s`,
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
        text: `[${fmtTs(ev.ts)}] DB     ready  database explorer unlocked`,
        level: "dim",
        severity: "dim",
        kind: "db",
        compactable: false,
        groupKey: "db-ready",
        isResumeRelated: false,
        isResumeNoOp: false,
      })

    case "done":
      return finalize({
        text: `[${fmtTs(eventTs(ev))}] DONE   Review complete.`,
        level: "info",
        severity: "info",
        kind: "done",
        compactable: false,
        groupKey: "done:review",
        isResumeRelated: false,
        isResumeNoOp: false,
      })

    case "error":
      return finalize({
        text: `[${fmtTs(eventTs(ev))}] ERROR  ${ev.msg}`,
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
        text: `[${fmtTs(eventTs(ev))}] CANCEL Review cancelled.`,
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
      return finalize({
        text: `[${fmtTs(ev.ts)}] FUNNEL ${deduped} deduped -> ${afterMetadata} after metadata -> ${toLlm} to LLM (${autoExcl} auto-excluded)`,
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

    case "batch_screen_done": {
      const bs = ev as unknown as Record<string, number>
      const scored = bs.scored ?? 0
      const forwarded = bs.forwarded ?? 0
      const excluded = bs.excluded ?? 0
      const thresholdLabel = asPercentLabel(typeof bs.threshold === "number" ? bs.threshold : null)
      const skipNote = bs.skipped_resume ? ` (${bs.skipped_resume} skipped-resume)` : ""
      return finalize({
        text: `[${fmtTs(ev.ts)}] BATCH  ${scored} batch-ranked -> ${forwarded} to dual-reviewer, ${excluded} auto-excluded (score < ${thresholdLabel})${skipNote}`,
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

    default:
      return finalize({
        text: `[${fmtTs(eventTs(ev))}] ${ev.type}`,
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
