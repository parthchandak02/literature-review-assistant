import { describe, expect, it } from "vitest"
import {
  auditStatusToVariant,
  confidenceToVariant,
  humanizeReason,
  INTERLEAVED_PHASE_MILESTONE,
  isProsperoRegistrationNumberValid,
  milestoneForPhase,
  milestoneLabelForPhase,
  phaseColor,
  PHASE_MILESTONES,
  PHASE_ORDER,
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
    expect(resolveRunStatus("awaiting_review")).toBe("awaiting_review")
    expect(resolveRunStatus("awaiting_prospero")).toBe("awaiting_prospero")
    expect(resolveRunStatus("config_generating")).toBe("config_generating")
    expect(resolveRunStatus("config_ready")).toBe("config_ready")
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

  it("validates PROSPERO registration number format", () => {
    expect(isProsperoRegistrationNumberValid("CRD42025678901")).toBe(true)
    expect(isProsperoRegistrationNumberValid("crd42025678901")).toBe(true)
    expect(isProsperoRegistrationNumberValid("CRD123")).toBe(false)
    expect(isProsperoRegistrationNumberValid("")).toBe(false)
  })

  it("keeps resume phase order parity contract (no removed phases)", () => {
    expect(RESUME_PHASE_ORDER).toEqual([
      "phase_1_prospero_gate",
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

describe("phase milestones", () => {
  it("defines 7 milestones aligned with activity log sections", () => {
    expect(PHASE_MILESTONES).toHaveLength(7)
    expect(PHASE_MILESTONES.map((milestone) => milestone.key)).toEqual([
      "start",
      "prospero",
      "discovery",
      "evidence",
      "synthesis",
      "manuscript",
      "finalize",
    ])
  })

  it("maps every canonical phase order entry to a milestone", () => {
    for (const phase of PHASE_ORDER) {
      expect(milestoneForPhase(phase)).not.toBeNull()
    }
  })

  it("maps common interleaved phases to the correct milestone", () => {
    expect(milestoneForPhase("screening_calibration")?.key).toBe("discovery")
    expect(milestoneForPhase("human_review_checkpoint")?.key).toBe("discovery")
    expect(milestoneForPhase("citation_chasing")?.key).toBe("discovery")
    expect(milestoneForPhase("phase_6_humanizer")?.key).toBe("manuscript")
    expect(milestoneForPhase("phase_6a_hyde")?.key).toBe("manuscript")
    expect(milestoneForPhase("resume")?.key).toBe("start")
  })

  it("maps prospero gate to the prospero milestone", () => {
    const milestone = milestoneForPhase("phase_1_prospero_gate")
    expect(milestone?.key).toBe("prospero")
    expect(milestone?.label).toBe("PROSPERO")
    expect(milestoneLabelForPhase("phase_1_prospero_gate")).toBe("PROSPERO")
  })

  it("keeps interleaved map keys in sync with milestone helpers", () => {
    for (const [phase, expectedKey] of Object.entries(INTERLEAVED_PHASE_MILESTONE)) {
      expect(milestoneForPhase(phase)?.key).toBe(expectedKey)
    }
  })
})
