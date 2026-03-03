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
// Event -> log line conversion
// ---------------------------------------------------------------------------

export function eventToLogLine(ev: ReviewEvent): { text: string; level: "info" | "warn" | "error" | "dim" } {
  switch (ev.type) {
    case "phase_start":
      return {
        text: `[${fmtTs(ev.ts)}] PHASE  ${ev.phase}${ev.description ? "  " + ev.description : ""}`,
        level: "info",
      }
    case "phase_done":
      return { text: `[${fmtTs(ev.ts)}] DONE   ${ev.phase}`, level: "info" }
    case "progress":
      return { text: `[${fmtTs(ev.ts)}] PROG   ${ev.phase}: ${ev.current}/${ev.total}`, level: "dim" }
    case "api_call":
      return {
        text: `[${fmtTs(ev.ts)}] LLM    ${ev.status.toUpperCase().padEnd(7)} ${ev.source} | ${ev.call_type}${ev.model ? " | " + ev.model.split(":").pop() : ""}${ev.latency_ms != null ? " | " + ev.latency_ms + "ms" : ""}${ev.cost_usd != null && ev.cost_usd > 0 ? " | $" + ev.cost_usd.toFixed(4) : ""}`,
        level: ev.status === "success" ? "dim" : "error",
      }
    case "connector_result":
      return {
        text: `[${fmtTs(ev.ts)}] SEARCH ${ev.status === "success" ? "OK     " : "FAIL   "} ${ev.name}: ${ev.status === "success" ? ev.records + " records" : (ev.error ?? "unknown error")}`,
        level: ev.status === "success" ? "dim" : "warn",
      }
    case "screening_decision": {
      const conf = (ev as { confidence?: number }).confidence
      const confStr = conf != null ? ` (${conf.toFixed(2)})` : ""
      return {
        text: `[${fmtTs(ev.ts)}] SCREEN ${String(ev.decision).toUpperCase().padEnd(7)} ${ev.stage} | ${ev.paper_id?.slice(0, 16) ?? ""}${confStr}`,
        level: ev.decision === "include" ? "info" : "dim",
      }
    }
    case "extraction_paper":
      return {
        text: `[${fmtTs(ev.ts)}] EXTRACT        ${ev.paper_id?.slice(0, 16) ?? ""} design=${ev.design} rob=${ev.rob_judgment}`,
        level: "dim",
      }
    case "synthesis":
      return {
        text: `[${fmtTs(ev.ts)}] SYNTH  feasible=${ev.feasible} groups=${ev.groups} n=${ev.n_studies}`,
        level: "info",
      }
    case "rate_limit_wait":
      return {
        text: `[${fmtTs(ev.ts)}] RATELIMIT ${ev.tier}: ${ev.slots_used}/${ev.limit} -- waiting`,
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
