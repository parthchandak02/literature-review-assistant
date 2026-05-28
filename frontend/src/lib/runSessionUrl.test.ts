import { describe, expect, it } from "vitest"
import { parseRunUrl } from "./runSessionUrl"

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

  it("falls back invalid tab to activity", () => {
    expect(parseRunUrl("/run/wf-0102/not-a-tab")).toEqual({
      workflowId: "wf-0102",
      tab: "activity",
    })
  })

  it("returns null for non-run paths", () => {
    expect(parseRunUrl("/")).toBeNull()
    expect(parseRunUrl("/settings")).toBeNull()
  })
})
