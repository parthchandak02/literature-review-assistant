import { describe, expect, it } from "vitest"
import type { RunTab } from "@/context/runSessionTypes"
import { VALID_RUN_TABS, parseRunUrl } from "./runSessionUrl"

const ALL_RUN_TABS: RunTab[] = [
  "activity",
  "results",
  "database",
  "cost",
  "config",
  "review-screening",
]

describe("parseRunUrl", () => {
  it("parses workflow and default activity tab", () => {
    expect(parseRunUrl("/run/wf-0102")).toEqual({
      workflowId: "wf-0102",
      tab: "activity",
    })
  })

  it("parses explicit tab", () => {
    expect(parseRunUrl("/run/wf-0102/results")).toEqual({
      workflowId: "wf-0102",
      tab: "results",
    })
  })

  it("parses every primary RunTab segment", () => {
    for (const tab of ALL_RUN_TABS) {
      expect(parseRunUrl(`/run/wf-test/${tab}`)).toEqual({
        workflowId: "wf-test",
        tab,
      })
    }
  })

  it("falls back invalid tab to activity", () => {
    expect(parseRunUrl("/run/wf-0102/not-a-tab")).toEqual({
      workflowId: "wf-0102",
      tab: "activity",
    })
  })

  it("aliases removed tabs to results", () => {
    expect(parseRunUrl("/run/wf-0102/quality")).toEqual({
      workflowId: "wf-0102",
      tab: "results",
    })
    expect(parseRunUrl("/run/wf-0102/references")).toEqual({
      workflowId: "wf-0102",
      tab: "results",
    })
  })

  it("returns null for non-run paths", () => {
    expect(parseRunUrl("/")).toBeNull()
    expect(parseRunUrl("/settings")).toBeNull()
  })
})

describe("VALID_RUN_TABS", () => {
  it("matches RunTab union from runSessionTypes", () => {
    const fromSet = [...VALID_RUN_TABS].sort()
    const expected = [...ALL_RUN_TABS].sort()
    expect(fromSet).toEqual(expected)
  })
})
