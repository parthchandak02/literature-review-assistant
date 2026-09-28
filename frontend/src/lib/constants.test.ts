import { describe, expect, it } from "vitest"
import {
  auditStatusToVariant,
  confidenceToVariant,
  humanizeReason,
  INTERLEAVED_PHASE_MILESTONE,
  isPhaseId,
  isProsperoRegistrationNumberValid,
  milestoneForPhase,
  milestoneLabelForPhase,
  phaseColor,
  PHASE_IDS,
  type PhaseId,
  PHASE_LABEL_MAP,
  PHASE_LABELS,
  phaseLabel,
  PHASE_META,
  PHASE_MILESTONES,
  PHASE_ORDER,
  PHASE_SHORT_LABELS,
  phasesInMilestone,
  prismaStatusToVariant,
  RESUME_PHASE_ORDER,
  resolvePhaseId,
  resolveRunHeaderStatus,
  resolveRunStatus,
  screeningDecisionToVariant,
  STATUS_PROGRESS,
  STATUS_TEXT,
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

describe("PHASE_META single label source", () => {
  it("derives PHASE_LABELS, PHASE_SHORT_LABELS and PHASE_LABEL_MAP from PHASE_META", () => {
    for (const id of PHASE_IDS) {
      expect(PHASE_LABELS[id]).toBe(PHASE_META[id].long)
      expect(PHASE_SHORT_LABELS[id]).toBe(PHASE_META[id].short)
      expect(PHASE_LABEL_MAP[id]).toBe(PHASE_META[id].short)
    }
    expect(PHASE_LABEL_MAP.quality_rob2).toBe("RoB 2")
    expect(PHASE_LABEL_MAP.phase_4_extraction_quality).toBe("Extraction")
  })

  it("covers every timeline, resume and sub-phase checkpoint id", () => {
    const backendIds = [
      ...PHASE_ORDER,
      ...RESUME_PHASE_ORDER,
      "phase_7_audit",
      "phase_3b_fulltext",
      "phase_6a_hyde",
      "phase_6a2_outline",
      "phase_6b_phase_a",
      "phase_6c_phase_b",
      "phase_6d_assembly",
      "phase_6e_concepts",
      "phase_6f_custom_diagrams",
    ]
    for (const id of backendIds) expect(isPhaseId(id), id).toBe(true)
  })

  it("keeps milestone phases consistent with PHASE_META", () => {
    for (const milestone of PHASE_MILESTONES) {
      for (const phase of milestone.phases) {
        expect(PHASE_META[phase].milestone).toBe(milestone.key)
      }
    }
  })

  it("lists every phase of a milestone, timeline phases first", () => {
    expect(phasesInMilestone("discovery").slice(0, 3)).toEqual([
      "phase_2_search",
      "phase_3_screening",
      "fulltext_pdf_retrieval",
    ])
    expect(phasesInMilestone("discovery")).toContain("screening_calibration")
    expect(phasesInMilestone("manuscript")[0]).toBe("phase_6_writing")
    expect(phasesInMilestone("manuscript")).toContain("phase_6f_custom_diagram_drawing")
    expect(phasesInMilestone("evidence")).toContain("quality_mmat")
    const all = PHASE_MILESTONES.flatMap((milestone) => phasesInMilestone(milestone.key))
    expect(new Set(all).size).toBe(all.length)
    const labelKey = (id: PhaseId) => `${PHASE_META[id].short}|${PHASE_META[id].long}`
    const covered = new Set(all.map(labelKey))
    expect(PHASE_IDS.every((id) => covered.has(labelKey(id)))).toBe(true)
  })

  it("collapses alias ids with identical labels to the canonical checkpoint id", () => {
    const manuscript = phasesInMilestone("manuscript")
    expect(manuscript).toContain("phase_6a_hyde")
    expect(manuscript).not.toContain("phase_6_hyde")
    expect(manuscript).toContain("phase_6a2_outline")
    expect(manuscript).not.toContain("phase_6_writing_outline")
    expect(manuscript).toContain("phase_6e_concepts")
    expect(manuscript).not.toContain("phase_6e_concept_diagram")
    const labels = manuscript.map((id) => PHASE_META[id].long)
    expect(new Set(labels).size).toBe(labels.length)
  })

  it("maps cost-record and unknown numbered phases to milestones", () => {
    expect(milestoneForPhase("phase_6f_custom_diagram_drawing")?.key).toBe("manuscript")
    expect(milestoneForPhase("quality_rob2")?.key).toBe("evidence")
    expect(milestoneForPhase("screening_batch_ranker")?.key).toBe("discovery")
    expect(milestoneForPhase("phase_5_future_step")?.key).toBe("synthesis")
    expect(milestoneForPhase("phase_6x_new")?.key).toBe("manuscript")
    expect(milestoneForPhase("unknown_phase")).toBeNull()
  })
})

describe("phaseLabel", () => {
  it("returns long labels by default and short on request", () => {
    expect(phaseLabel("phase_4_extraction_quality")).toBe("Data extraction and quality appraisal")
    expect(phaseLabel("phase_4_extraction_quality", "short")).toBe("Extraction")
    expect(phaseLabel("phase_6_humanizer")).toBe("Humanizer pass")
    expect(phaseLabel("quality_mmat")).toBe("Quality appraisal (MMAT)")
    expect(phaseLabel("phase_6f_custom_diagrams")).toBe("Custom diagrams")
  })

  it("resolves raw backend and display-formatted phase strings", () => {
    expect(phaseLabel("phase_6f_custom_diagram_drawing")).toBe("Custom diagrams: drawing")
    expect(phaseLabel("Phase 6f Custom Diagram Drawing")).toBe("Custom diagrams: drawing")
    expect(phaseLabel("PHASE_6_HYDE")).toBe("Retrieval query drafting (HyDE)")
    expect(phaseLabel("phase_2_search_extra", "short")).toBe("Search")
    expect(resolvePhaseId("phase-3-screening")).toBe("phase_3_screening")
    expect(resolvePhaseId("")).toBeNull()
  })

  it("falls back to a sentence-cased label without the phase prefix", () => {
    expect(phaseLabel("phase_9_custom_step")).toBe("Custom step")
    expect(phaseLabel("phase_8b_new_thing")).toBe("New thing")
    expect(phaseLabel("quality_new_tool")).toBe("New tool")
    expect(phaseLabel("some_other_phase")).toBe("Some other phase")
    expect(phaseLabel("")).toBe("")
  })
})

describe("resolveRunHeaderStatus", () => {
  const base = {
    isDone: false,
    isRunning: false,
    isCancelled: false,
    isFailed: false,
    isAwaitingReview: false,
  }

  it("uses real labels instead of falling back to Ready", () => {
    expect(resolveRunHeaderStatus({ ...base, status: "stale" })).toEqual({
      label: "Stale",
      className: STATUS_TEXT.stale,
    })
    expect(resolveRunHeaderStatus({ ...base, status: "config_generating", isAwaitingProspero: true }).label).toBe(
      "Generating config",
    )
    expect(resolveRunHeaderStatus({ ...base, status: "config_ready", isAwaitingProspero: true }).label).toBe(
      "Config ready",
    )
    expect(resolveRunHeaderStatus({ ...base, status: "config_ready" }).label).toBe("Config ready")
    expect(resolveRunHeaderStatus({ ...base, status: "mystery_state" })).toEqual({
      label: "Mystery state",
      className: STATUS_TEXT.idle,
    })
  })

  it("keeps existing gate and terminal precedence", () => {
    expect(resolveRunHeaderStatus({ ...base, status: "awaiting_prospero", isAwaitingProspero: true }).label).toBe(
      "PROSPERO pending",
    )
    expect(resolveRunHeaderStatus({ ...base, status: "awaiting_review", isAwaitingReview: true })).toEqual({
      label: "Awaiting review",
      className: STATUS_TEXT.awaiting_review,
    })
    expect(resolveRunHeaderStatus({ ...base, status: "streaming", isRunning: true }).label).toBe("Running")
    expect(resolveRunHeaderStatus({ ...base, status: "done", isDone: true }).label).toBe("Completed")
    expect(resolveRunHeaderStatus({ ...base, status: "idle" }).label).toBe("Ready")
    expect(resolveRunHeaderStatus({ ...base, status: "" }).label).toBe("Ready")
  })
})
