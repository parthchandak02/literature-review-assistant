import { describe, expect, it } from "vitest"
import type { ReviewEvent } from "@/lib/api"
import { humanizeLogTag } from "@/lib/humanize"
import {
  eventToLogEntry,
  filterEventsBySeverity,
  matchesSeverityFilter,
  truncateWithEllipsis,
} from "./logLine"

const TS = "2026-03-12T00:00:00Z"

function apiCall(overrides: Partial<Extract<ReviewEvent, { type: "api_call" }>> = {}): ReviewEvent {
  return {
    type: "api_call",
    source: "screening",
    status: "success",
    phase: "phase_3_screening",
    call_type: "screen",
    model: "fireworks:accounts/fireworks/models/deepseek-v4-pro-0813",
    paper_id: null,
    latency_ms: 120,
    tokens_in: 10,
    tokens_out: 5,
    cost_usd: 0.001,
    records: null,
    details: null,
    section_name: null,
    word_count: null,
    ts: TS,
    ...overrides,
  }
}

describe("eventToLogEntry labels", () => {
  it("shows the short phase label for progress instead of the raw id", () => {
    const entry = eventToLogEntry({ type: "progress", phase: "phase_2_search", current: 3, total: 9, ts: TS })
    expect(entry.tag).toBe("PROG")
    expect(entry.message).toBe("Search: 3/9")
    expect(entry.message).not.toContain("phase_2_search")
  })

  it("exposes a readable tag label and glossary description", () => {
    const entry = eventToLogEntry({
      type: "search_override_status",
      database: "pubmed",
      status: "miss",
      detail: "query not applied",
      ts: TS,
    })
    expect(entry.tag).toBe("SRCHOV")
    expect(humanizeLogTag(entry.tag).label).toBe("Search override")
    expect(humanizeLogTag(entry.tag).description).not.toBe("")
    expect(entry.message).toBe("pubmed: missed -- query not applied")
  })

  it("spells out risk of bias for extraction rows", () => {
    const entry = eventToLogEntry({
      type: "extraction_paper",
      paper_id: "p1",
      design: "rct",
      rob_judgment: "some_concerns",
      ts: TS,
    })
    expect(entry.message).toContain("risk of bias: Some concerns")
    expect(entry.message).not.toContain("rob=")
  })

  it("shortens model paths and keeps the full path in detail", () => {
    const entry = eventToLogEntry(apiCall())
    expect(entry.message).toContain("· deepseek-v4-pro")
    expect(entry.message).not.toContain("accounts/fireworks")
    expect(entry.detail).toBe("Model: fireworks:accounts/fireworks/models/deepseek-v4-pro-0813")
  })

  it("formats API calls as readable segments and drops the implied success status", () => {
    const entry = eventToLogEntry(
      apiCall({
        source: "writing",
        call_type: "llm_outline",
        latency_ms: 8401,
        tokens_in: 10315,
        tokens_out: 1092,
        cost_usd: 0.0179,
      }),
    )
    expect(entry.message).toBe("Writing · outline · deepseek-v4-pro · 8.4s · 10.3K in / 1.1K out · $0.0179")
    expect(entry.level).toBe("dim")
    expect(entry.text).toContain("success | writing | llm_outline")
    expect(entry.text).toContain("8401ms")
  })

  it("keeps acronyms, section names and skips a call type that repeats the source", () => {
    const rag = eventToLogEntry(
      apiCall({ source: "writing", call_type: "rag_retrieval", section_name: "methods", latency_ms: 39370, tokens_in: 0, cost_usd: null }),
    )
    expect(rag.message).toBe("Writing · RAG retrieval · deepseek-v4-pro · methods section · 39.4s")
    const writing = eventToLogEntry(apiCall({ source: "writing", call_type: "writing", latency_ms: 120, tokens_in: 0, cost_usd: 0 }))
    expect(writing.message).toBe("Writing · deepseek-v4-pro · 120ms")
  })

  it("leads with the status and uses the error style for failed calls", () => {
    const entry = eventToLogEntry(apiCall({ status: "failed" }))
    expect(entry.message.startsWith("Failed · Screening · screen")).toBe(true)
    expect(entry.level).toBe("error")
    expect(entry.severity).toBe("error")
  })

  it("humanizes unknown event types in the default case", () => {
    const entry = eventToLogEntry({ type: "some_new_event", ts: TS } as unknown as ReviewEvent)
    expect(entry.message).toBe("Some new event")
    expect(entry.tag).toBe("...")
  })

  it("decodes HTML entities in titles", () => {
    const decision = eventToLogEntry({
      type: "screening_decision",
      paper_id: "p1",
      stage: "title_abstract",
      decision: "include",
      title: "Students&amp;apos; outcomes",
      ts: TS,
    })
    expect(decision.message).toContain("Students' outcomes")
    const pdf = eventToLogEntry({
      type: "pdf_result",
      paper_id: "p1",
      title: "A &lt;b&gt; study",
      source: "unpaywall",
      success: true,
      ts: TS,
    })
    expect(pdf.message).toContain("A <b> study")
  })

  it("marks truncated reasons with an ellipsis and keeps the full reason in detail", () => {
    const reason = "x".repeat(150)
    const entry = eventToLogEntry({
      type: "screening_decision",
      paper_id: "p1",
      stage: "title_abstract",
      decision: "exclude",
      method: "heuristic",
      reason_label: reason,
      reason: "custom",
      ts: TS,
    })
    expect(entry.message.endsWith("…")).toBe(true)
    expect(entry.detail).toBe(`Reason: ${reason}`)
    expect(entry.subTag).toBe("AUTO")
    expect(entry.ts).not.toBe("")
  })

  it("keeps a searchable text line with timestamp, tag and message", () => {
    const entry = eventToLogEntry({ type: "warn", message: "Slow connector", ts: TS })
    expect(entry.text).toMatch(/^\[\d{2}:\d{2}:\d{2}\] WARN Slow connector$/)
    expect(entry.level).toBe("warn")
  })
})

describe("truncateWithEllipsis", () => {
  it("leaves short text alone and ends long text with an ellipsis", () => {
    expect(truncateWithEllipsis("short", 10)).toBe("short")
    const out = truncateWithEllipsis("abcdefghijkl", 6)
    expect(out).toBe("abcde…")
    expect(out.length).toBe(6)
  })
})

describe("severity filter", () => {
  it("matches severities per chip", () => {
    expect(matchesSeverityFilter("info", "all")).toBe(true)
    expect(matchesSeverityFilter("warn", "warnings")).toBe(true)
    expect(matchesSeverityFilter("error", "warnings")).toBe(true)
    expect(matchesSeverityFilter("info", "warnings")).toBe(false)
    expect(matchesSeverityFilter("warn", "errors")).toBe(false)
    expect(matchesSeverityFilter("error", "errors")).toBe(true)
    expect(matchesSeverityFilter("decision", "decisions")).toBe(true)
    expect(matchesSeverityFilter("error", "decisions")).toBe(false)
  })

  it("filters events but keeps phase_start for grouping", () => {
    const events: ReviewEvent[] = [
      { type: "phase_start", phase: "phase_3_screening", description: "", total: null, ts: TS },
      { type: "status", message: "working", ts: TS },
      { type: "warn", message: "careful", ts: TS },
      { type: "error", msg: "boom", ts: TS },
      apiCall({ status: "error" }),
      { type: "screening_decision", paper_id: "p1", stage: "title_abstract", decision: "include", ts: TS },
    ]
    expect(filterEventsBySeverity(events, "all")).toBe(events)
    expect(filterEventsBySeverity(events, "warnings").map((e) => e.type)).toEqual([
      "phase_start",
      "warn",
      "error",
      "api_call",
    ])
    expect(filterEventsBySeverity(events, "errors").map((e) => e.type)).toEqual(["phase_start", "error", "api_call"])
    expect(filterEventsBySeverity(events, "decisions").map((e) => e.type)).toEqual([
      "phase_start",
      "screening_decision",
    ])
  })
})
