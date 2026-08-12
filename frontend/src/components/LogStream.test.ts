import { describe, expect, it } from "vitest"
import { buildRenderItems } from "./LogStream"
import type { ReviewEvent } from "@/lib/api"

function seps(items: ReturnType<typeof buildRenderItems>) {
  return items.filter((item) => item.kind === "phase-sep")
}

function events(items: ReturnType<typeof buildRenderItems>) {
  return items.filter((item) => item.kind === "event")
}

describe("buildRenderItems milestone grouping", () => {
  it("opens Start separator for pre-phase events", () => {
    const items = buildRenderItems([
      { type: "db_ready", ts: "2026-03-12T00:00:00Z" },
      { type: "status", message: "Bootstrapping", ts: "2026-03-12T00:00:01Z" },
    ])

    expect(seps(items)).toEqual([
      expect.objectContaining({ kind: "phase-sep", phase: "start", label: "Start" }),
    ])
    expect(events(items)).toHaveLength(2)
  })

  it("emits milestone separator on milestone change, not every phase_start", () => {
    const reviewEvents: ReviewEvent[] = [
      {
        type: "phase_start",
        phase: "phase_2_search",
        description: "Search databases",
        total: null,
        ts: "2026-03-12T00:00:00Z",
      },
      {
        type: "phase_start",
        phase: "phase_3_screening",
        description: "Screen titles and abstracts",
        total: null,
        ts: "2026-03-12T00:01:00Z",
      },
      {
        type: "progress",
        phase: "phase_3_screening",
        current: 1,
        total: 10,
        ts: "2026-03-12T00:02:00Z",
      },
    ]

    const items = buildRenderItems(reviewEvents)
    const separators = seps(items)

    expect(separators).toHaveLength(1)
    expect(separators[0]).toMatchObject({
      phase: "discovery",
      label: "Discovery",
      description: "Search databases",
    })
    expect(events(items).map((item) => item.ev.type)).toEqual(["progress"])
  })

  it("advances separators when milestone changes and keeps phase_start out of rows", () => {
    const items = buildRenderItems([
      {
        type: "phase_start",
        phase: "phase_1_prospero_gate",
        description: "Register protocol",
        total: null,
        ts: "2026-03-12T00:00:00Z",
      },
      {
        type: "phase_start",
        phase: "phase_2_search",
        description: "Search databases",
        total: null,
        ts: "2026-03-12T00:01:00Z",
      },
      {
        type: "connector_result",
        name: "pubmed",
        status: "ok",
        records: 42,
        error: null,
        ts: "2026-03-12T00:02:00Z",
      },
    ])

    expect(seps(items).map((sep) => ({ phase: sep.phase, label: sep.label }))).toEqual([
      { phase: "prospero", label: "PROSPERO" },
      { phase: "discovery", label: "Discovery" },
    ])
    expect(events(items).map((item) => item.ev.type)).toEqual(["connector_result"])
  })

  it("infers milestone from event type after workflow phases begin", () => {
    const items = buildRenderItems([
      {
        type: "phase_start",
        phase: "phase_4_extraction_quality",
        description: "Extract study data",
        total: null,
        ts: "2026-03-12T00:00:00Z",
      },
      {
        type: "extraction_paper",
        paper_id: "p1",
        design: "rct",
        rob_judgment: "low",
        ts: "2026-03-12T00:01:00Z",
      },
    ])

    expect(seps(items)).toHaveLength(1)
    expect(seps(items)[0]).toMatchObject({ phase: "evidence", label: "Evidence Build" })
    expect(events(items)).toHaveLength(1)
  })
})
