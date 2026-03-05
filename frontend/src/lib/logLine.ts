import type { ReviewEvent } from "@/lib/api"

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
    return new Date(ts).toLocaleTimeString("en-US", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    })
  } catch {
    return ts.slice(11, 19)
  }
}

// ---------------------------------------------------------------------------
// Level type
// ---------------------------------------------------------------------------

export type LogLevel = "info" | "warn" | "error" | "dim" | "include" | "exclude" | "exclude-heuristic" | "status"

// ---------------------------------------------------------------------------
// Event -> log line conversion
// ---------------------------------------------------------------------------

export function eventToLogLine(ev: ReviewEvent): { text: string; level: LogLevel } {
  switch (ev.type) {
    case "phase_start":
      return {
        text: `[${fmtTs(ev.ts)}] PHASE  ${ev.phase}${ev.description ? "  " + ev.description : ""}`,
        level: "info",
      }

    case "phase_done": {
      const s = ev.summary as Record<string, unknown> | null | undefined
      let detail = ""
      if (s?.included != null && s?.screened != null)
        detail = `  ${s.included} included of ${s.screened} papers`
      else if (s?.new_papers != null)
        detail = `  ${Number(s.new_papers) > 0 ? s.new_papers + " new papers found" : "no new papers"}`
      else if (s?.records != null)
        detail = `  ${s.records} records`
      else if (s?.papers != null)
        detail = `  ${s.papers} papers`
      return { text: `[${fmtTs(ev.ts)}] DONE   ${ev.phase}${detail}`, level: "info" }
    }

    case "progress":
      return { text: `[${fmtTs(ev.ts)}] PROG   ${ev.phase}: ${ev.current}/${ev.total}`, level: "dim" }

    case "status":
      return {
        text: `[${fmtTs(ev.ts)}] ...    ${ev.message}`,
        level: "status",
      }

    case "screening_calibration": {
      const inc = Math.round(ev.include_threshold * 100)
      const exc = Math.round(ev.exclude_threshold * 100)
      return {
        text: `[${fmtTs(ev.ts)}] CALIB  include>=${inc}%  exclude<=${exc}%  kappa=${ev.kappa.toFixed(2)}  n=${ev.sample_size}`,
        level: "info",
      }
    }

    case "api_call":
      return {
        text: `[${fmtTs(ev.ts)}] LLM    ${ev.status.toUpperCase().padEnd(7)} ${ev.source} | ${ev.call_type}${ev.model ? " | " + ev.model.split(":").pop() : ""}${ev.section_name ? " | section=" + ev.section_name : ""}${ev.latency_ms != null ? " | " + ev.latency_ms + "ms" : ""}${ev.cost_usd != null && ev.cost_usd > 0 ? " | $" + ev.cost_usd.toFixed(4) : ""}`,
        level: ev.status === "success" ? "dim" : "error",
      }

    case "connector_result":
      return {
        text: `[${fmtTs(ev.ts)}] SEARCH ${ev.status === "success" ? "OK     " : "FAIL   "} ${ev.name}: ${ev.status === "success" ? ev.records + " records" : (ev.error ?? "unknown error")}`,
        level: ev.status === "success" ? "info" : "warn",
      }

    case "screening_decision": {
      const REASON_LABELS: Record<string, string> = {
        insufficient_content_heuristic: "auto-excluded: abstract absent or too short",
        protocol_only_heuristic: "auto-excluded: conference-only abstract",
      }
      const conf = ev.confidence != null ? ` ${Math.round(ev.confidence * 100)}%` : ""
      const label = ev.title ?? ev.paper_id?.slice(0, 32) ?? ""
      const rawReason = ev.reason ?? ""
      const displayReason = rawReason ? (REASON_LABELS[rawReason] ?? rawReason).slice(0, 90) : ""
      const reasonText = displayReason ? `  -- ${displayReason}` : ""
      const methodBadge = ev.method === "heuristic" ? "[AUTO]  " : "[LLM]   "
      const verb = ev.decision === "include" ? "INCLUDE" : "EXCLUDE"
      return {
        text: `[${fmtTs(ev.ts)}] ${verb.padEnd(7)} ${methodBadge}${label}${conf}${reasonText}`,
        level: ev.decision === "include" ? "include" : ev.method === "heuristic" ? "exclude-heuristic" : "exclude",
      }
    }

    case "extraction_paper":
      return {
        text: `[${fmtTs(ev.ts)}] EXTRACT ${ev.paper_id?.slice(0, 16) ?? ""}  design=${ev.design}  rob=${ev.rob_judgment}`,
        level: "dim",
      }

    case "synthesis":
      return {
        text: `[${fmtTs(ev.ts)}] SYNTH  feasible=${ev.feasible}  groups=${ev.groups}  n=${ev.n_studies}`,
        level: "info",
      }

    case "rate_limit_wait":
      return {
        text: `[${fmtTs(ev.ts)}] RATELIMIT  ${ev.tier}: ${ev.slots_used}/${ev.limit} slots -- waiting`,
        level: "warn",
      }

    case "db_ready":
      return {
        text: `[${fmtTs(ev.ts)}] DB     ready  database explorer unlocked`,
        level: "dim",
      }

    case "done":
      return {
        text: `[${fmtTs(ev.ts)}] DONE   Review complete.`,
        level: "info",
      }

    case "error":
      return {
        text: `[${fmtTs(ev.ts)}] ERROR  ${ev.msg}`,
        level: "error",
      }

    case "cancelled":
      return {
        text: `[${fmtTs(ev.ts)}] CANCEL Review cancelled.`,
        level: "warn",
      }

    default:
      return { text: `[${fmtTs("ts" in ev ? (ev as { ts?: string }).ts : undefined)}] ${ev.type}`, level: "dim" }
  }
}
