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

const PHASE_LABELS: Record<string, string> = {
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
  phase_6_writing: "Writing",
  finalize: "Finalize",
}

export function eventToLogLine(ev: ReviewEvent): { text: string; level: LogLevel } {
  switch (ev.type) {
    case "phase_start": {
      const label = PHASE_LABELS[ev.phase as string] ?? ev.phase
      return {
        text: `[${fmtTs(ev.ts)}] PHASE  ${label}${ev.description ? "  " + ev.description : ""}`,
        level: "info",
      }
    }

    case "phase_done": {
      const s = ev.summary as Record<string, unknown> | null | undefined
      let detail = ""
      if (s?.included != null && s?.screened != null)
        detail = `  ${s.included} included of ${s.screened} papers`
      else if (s?.new_papers != null)
        detail = `  ${Number(s.new_papers) > 0 ? s.new_papers + " new papers found" : "no new papers"}`
      else if (s?.fetched != null)
        detail = `  ${s.fetched} papers`
      else if (s?.records != null)
        detail = `  ${s.records} records`
      else if (s?.papers != null)
        detail = `  ${s.papers} papers`
      const phaseLabel = PHASE_LABELS[ev.phase as string] ?? ev.phase
      return { text: `[${fmtTs(ev.ts)}] DONE   ${phaseLabel}${detail}`, level: "info" }
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

    case "search_override_status": {
      const badge = ev.status === "applied" ? "OK    " : ev.status === "miss" ? "MISS  " : "ABSENT"
      const lvl: LogLevel = ev.status === "applied" ? "info" : "warn"
      return {
        text: `[${fmtTs(ev.ts)}] SRCHOV ${badge} ${ev.database}: ${ev.detail}`,
        level: lvl,
      }
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

    case "screening_prefilter_done": {
      const pf = ev as unknown as Record<string, number>
      const deduped = pf.deduped ?? 0
      const metaRej = pf.metadata_rejected ?? 0
      const autoExcl = pf.automation_excluded ?? 0
      const toLlm = pf.to_llm ?? 0
      return {
        text: `[${fmtTs(ev.ts)}] FUNNEL ${deduped} deduped -> ${deduped - metaRej} after metadata -> ${toLlm} to LLM (${autoExcl} auto-excluded)`,
        level: "info",
      }
    }

    case "batch_screen_done": {
      const bs = ev as unknown as Record<string, number>
      const scored = bs.scored ?? 0
      const forwarded = bs.forwarded ?? 0
      const excluded = bs.excluded ?? 0
      const threshold = typeof bs.threshold === "number" ? Math.round(bs.threshold * 100) : 35
      const skipNote = bs.skipped_resume ? ` (${bs.skipped_resume} skipped-resume)` : ""
      return {
        text: `[${fmtTs(ev.ts)}] BATCH  ${scored} batch-ranked -> ${forwarded} to dual-reviewer, ${excluded} auto-excluded (score < ${threshold}%)${skipNote}`,
        level: "info",
      }
    }

    default:
      return { text: `[${fmtTs("ts" in ev ? (ev as { ts?: string }).ts : undefined)}] ${ev.type}`, level: "dim" }
  }
}
