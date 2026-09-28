import { describe, expect, it } from "vitest"
import {
  defaultTabForStatus,
  explicitTabWorkflowId,
  orderRunTabs,
  resolveAutoRouteTab,
  resolveRunGate,
  shouldShowGateBanner,
} from "./runRouting"
import { parseRunUrl } from "@/lib/runSessionUrl"
import type { RunTab } from "@/context/runSessionTypes"

const base = { isAwaitingProspero: false, isAwaitingReview: false, isRunning: false }

describe("resolveRunGate", () => {
  it("maps gate statuses", () => {
    expect(resolveRunGate({ ...base, historicalStatus: "config_ready" })).toBe("config_ready")
    expect(resolveRunGate({ ...base, status: "config_ready" })).toBe("config_ready")
    expect(resolveRunGate({ ...base, isAwaitingProspero: true })).toBe("awaiting_prospero")
    expect(resolveRunGate({ ...base, isAwaitingReview: true })).toBe("awaiting_review")
  })

  it("returns null for non-gate states", () => {
    expect(resolveRunGate({ ...base, status: "done" })).toBeNull()
    expect(resolveRunGate({ ...base, status: "streaming", isRunning: true })).toBeNull()
    expect(resolveRunGate({ ...base, status: "config_generating", isAwaitingProspero: true })).toBe("config_generating")
  })
})

describe("defaultTabForStatus", () => {
  it("routes gates to their action tab", () => {
    expect(defaultTabForStatus("config_ready")).toBe("config")
    expect(defaultTabForStatus("awaiting_prospero")).toBe("config")
    expect(defaultTabForStatus("awaiting_review")).toBe("review-screening")
    expect(defaultTabForStatus(null)).toBe("activity")
  })
})

describe("resolveAutoRouteTab", () => {
  it("switches from the default tab to the gate tab", () => {
    expect(
      resolveAutoRouteTab({ gate: "awaiting_review", activeTab: "activity", explicitDeepLink: false }),
    ).toBe("review-screening")
    expect(
      resolveAutoRouteTab({ gate: "config_ready", activeTab: "activity", explicitDeepLink: false }),
    ).toBe("config")
  })

  it("keeps explicit deep links and non-default tabs", () => {
    expect(
      resolveAutoRouteTab({ gate: "awaiting_review", activeTab: "activity", explicitDeepLink: true }),
    ).toBeNull()
    expect(
      resolveAutoRouteTab({ gate: "awaiting_review", activeTab: "cost", explicitDeepLink: false }),
    ).toBeNull()
    expect(resolveAutoRouteTab({ gate: null, activeTab: "activity", explicitDeepLink: false })).toBeNull()
  })
})

describe("explicitTabWorkflowId", () => {
  it("detects an explicit tab segment without changing parseRunUrl", () => {
    expect(explicitTabWorkflowId("/run/wf-1/cost")).toBe("wf-1")
    expect(explicitTabWorkflowId("/run/wf-1/activity")).toBe("wf-1")
    expect(explicitTabWorkflowId("/run/wf-1")).toBeNull()
    expect(explicitTabWorkflowId("/")).toBeNull()
    expect(parseRunUrl("/run/wf-1")).toEqual({ workflowId: "wf-1", tab: "activity" })
  })
})

describe("shouldShowGateBanner", () => {
  it("hides on the action tab and when no gate", () => {
    expect(shouldShowGateBanner("awaiting_review", "activity")).toBe(true)
    expect(shouldShowGateBanner("awaiting_review", "config")).toBe(true)
    expect(shouldShowGateBanner("awaiting_review", "review-screening")).toBe(false)
    expect(shouldShowGateBanner("config_ready", "config")).toBe(false)
    expect(shouldShowGateBanner("awaiting_prospero", "results")).toBe(true)
    expect(shouldShowGateBanner(null, "activity")).toBe(false)
  })
})

describe("orderRunTabs", () => {
  const tabs: { id: RunTab }[] = [
    { id: "activity" },
    { id: "results" },
    { id: "database" },
    { id: "config" },
    { id: "cost" },
  ]

  it("puts the gate tab second", () => {
    expect(orderRunTabs(tabs, { id: "review-screening" }).map((t) => t.id)).toEqual([
      "activity",
      "review-screening",
      "results",
      "database",
      "config",
      "cost",
    ])
  })

  it("leaves order unchanged without a gate tab", () => {
    expect(orderRunTabs(tabs, null)).toEqual(tabs)
  })
})
