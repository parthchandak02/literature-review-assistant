import { describe, expect, it } from "vitest"
import {
  describeManuscriptContract,
  describeManuscriptGate,
  selectManuscriptAuditRun,
} from "./manuscriptAudit"
import type { ManuscriptAuditRun } from "./api"

function makeRun(overrides: Partial<ManuscriptAuditRun> = {}): ManuscriptAuditRun {
  return {
    audit_run_id: "audit-001",
    workflow_id: "wf-1",
    mode: "strict",
    verdict: "minor_revisions",
    passed: true,
    selected_profiles: ["general_systematic_review"],
    summary: "Summary",
    total_findings: 1,
    major_count: 0,
    minor_count: 1,
    note_count: 0,
    blocking_count: 0,
    contract_mode: "strict",
    contract_passed: true,
    contract_violation_count: 0,
    contract_violations: [],
    gate_blocked: false,
    gate_failure_reasons: [],
    total_cost_usd: 0.01,
    created_at: "2026-04-02T00:00:00Z",
    ...overrides,
  }
}

describe("manuscriptAudit helpers", () => {
  it("selects an explicit audit run when present in history", () => {
    const latest = makeRun({ audit_run_id: "audit-latest" })
    const older = makeRun({ audit_run_id: "audit-older", verdict: "major_revisions" })

    expect(selectManuscriptAuditRun(latest, [latest, older], "audit-older")?.audit_run_id).toBe("audit-older")
  })

  it("falls back to latest run when requested history entry is missing", () => {
    const latest = makeRun({ audit_run_id: "audit-latest" })

    expect(selectManuscriptAuditRun(latest, [latest], "missing")?.audit_run_id).toBe("audit-latest")
  })

  it("describes blocked gate and failed contract status", () => {
    const blocked = makeRun({
      passed: false,
      gate_blocked: true,
      contract_passed: false,
      contract_violation_count: 3,
    })

    expect(describeManuscriptGate(blocked)).toContain("blocked")
    expect(describeManuscriptContract(blocked)).toContain("failed")
    expect(describeManuscriptContract(blocked)).toContain("3 violation")
  })
})
