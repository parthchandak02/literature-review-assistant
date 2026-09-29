import { describe, expect, it } from "vitest"
import type { ReviewEvent } from "./api"
import { computeFunnelStages } from "./funnelStages"

function connector(name: string, records: number, status = "success"): ReviewEvent {
  return { type: "connector_result", name, status, records, error: null, ts: "2026-09-01T00:00:00Z" } as ReviewEvent
}

describe("computeFunnelStages identified stage", () => {
  it("counts only the last result per connector when a relaxed retry replaces the primary query", () => {
    const stages = computeFunnelStages([
      connector("ieee_xplore", 1),
      connector("pubmed", 64),
      connector("dblp", 0, "failed"),
      connector("ieee_xplore", 3),
      {
        type: "phase_done",
        phase: "phase_2_search",
        summary: { papers: 60 },
        total: null,
        completed: null,
        ts: "2026-09-01T00:00:00Z",
      } as ReviewEvent,
    ])
    expect(stages.find((s) => s.key === "identified")?.count).toBe(67)
  })
})

function phaseDone(phase: string, summary: Record<string, unknown>): ReviewEvent {
  return { type: "phase_done", phase, summary, total: null, completed: null, ts: "2026-09-01T00:00:00Z" } as ReviewEvent
}

describe("computeFunnelStages PRISMA definitions", () => {
  const wf0001: ReviewEvent[] = [
    connector("ieee_xplore", 1),
    connector("ieee_xplore", 3),
    phaseDone("phase_2_search", { papers: 1548, total_records: 1715, dedup: 167 }),
    {
      type: "screening_prefilter_done",
      deduped: 1548,
      metadata_rejected: 17,
      after_metadata: 1531,
      automation_excluded: 1311,
      to_llm: 220,
      ts: "",
    } as unknown as ReviewEvent,
    { type: "batch_screen_done", scored: 220, forwarded: 209, excluded: 11, ts: "" } as unknown as ReviewEvent,
    phaseDone("phase_3_screening", {
      included: 6,
      screened: 1548,
      excluded: 1542,
      fulltext_sought: 57,
      fulltext_not_retrieved: 50,
      fulltext_retrieved: 7,
    }),
  ]

  it("matches the PRISMA builder boxes for wf-0001", () => {
    const stages = computeFunnelStages(wf0001)
    expect(stages.map((s) => [s.key, s.count, s.kind])).toEqual([
      ["identified", 1715, "count"],
      ["duplicates", 167, "removed"],
      ["automation", 1339, "removed"],
      ["screened", 209, "count"],
      ["excluded_ta", 152, "removed"],
      ["sought", 57, "count"],
      ["not_retrieved", 50, "removed"],
      ["assessed", 7, "count"],
      ["excluded_ft", 1, "removed"],
      ["included", 6, "count"],
    ])
  })

  it("keeps every removal row equal to the gap between its count rows", () => {
    const stages = computeFunnelStages(wf0001)
    let running = stages[0].count
    for (const s of stages.slice(1)) {
      if (s.kind === "removed") running -= s.count
      else expect(s.count).toBe(running)
    }
  })

  it("uses the canonical included count and recomputes full-text exclusions", () => {
    const stages = computeFunnelStages(wf0001, 5)
    expect(stages.find((s) => s.key === "included")?.count).toBe(5)
    expect(stages.find((s) => s.key === "excluded_ft")?.count).toBe(2)
  })

  it("shows the after-dedup count before screening starts", () => {
    const stages = computeFunnelStages(wf0001.slice(0, 3))
    expect(stages.map((s) => s.key)).toEqual(["identified", "duplicates", "deduped"])
  })
})
