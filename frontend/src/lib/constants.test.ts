import { describe, expect, it } from "vitest"
import {
  auditStatusToVariant,
  confidenceToVariant,
  humanizeReason,
  phaseColor,
  prismaStatusToVariant,
  RESUME_PHASE_ORDER,
  resolveRunStatus,
  screeningDecisionToVariant,
  STATUS_PROGRESS,
} from "./constants"

describe("constants semantic mappings", () => {
  it("maps historical/backend statuses to canonical run status", () => {
    expect(resolveRunStatus("completed")).toBe("done")
    expect(resolveRunStatus("running")).toBe("streaming")
    expect(resolveRunStatus("awaiting_review")).toBe("streaming")
    expect(resolveRunStatus("interrupted")).toBe("cancelled")
    expect(resolveRunStatus("stale")).toBe("stale")
  })

  it("resolves token-backed phase colors", () => {
    expect(phaseColor("phase_2_search")).toBe("var(--color-phase-2-search)")
    expect(phaseColor("phase_2_search_extra")).toBe("var(--color-phase-2-search)")
    expect(phaseColor("unknown_phase")).toBe("var(--color-finalize)")
  })

  it("maps decision/confidence/audit/prisma statuses to badge variants", () => {
    expect(screeningDecisionToVariant("include")).toBe("success")
    expect(screeningDecisionToVariant("exclude")).toBe("danger")
    expect(confidenceToVariant(0.85)).toBe("success")
    expect(confidenceToVariant(0.6)).toBe("warning")
    expect(confidenceToVariant(0.2)).toBe("danger")
    expect(auditStatusToVariant("passed")).toBe("success")
    expect(prismaStatusToVariant("PARTIAL")).toBe("warning")
    expect(prismaStatusToVariant("NOT_APPLICABLE")).toBe("neutral")
  })

  it("humanizes reason labels from canonical map", () => {
    expect(humanizeReason("insufficient_content_heuristic")).toContain("Skipped")
    expect(humanizeReason("custom_reason_code")).toBe("custom reason code")
  })

  it("keeps status progress semantic class mapping", () => {
    expect(STATUS_PROGRESS.streaming).toBe("bg-intent-active")
    expect(STATUS_PROGRESS.done).toBe("bg-intent-success")
  })

  it("keeps resume phase order parity contract (no removed phases)", () => {
    expect(RESUME_PHASE_ORDER).toEqual([
      "phase_2_search",
      "phase_3_screening",
      "phase_4_extraction_quality",
      "phase_4b_embedding",
      "phase_5_synthesis",
      "phase_5b_knowledge_graph",
      "phase_5c_pre_writing_gate",
      "phase_6_writing",
      "finalize",
    ])
  })
})
