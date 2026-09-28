import { describe, expect, it } from "vitest"
import { auditItemsFromPayload, splitAuditSummary, type ManuscriptAuditPayload } from "./auditFindings"

const payload: ManuscriptAuditPayload = {
  run_id: "r",
  workflow_id: "wf",
  latest_run: {
    audit_run_id: "a1",
    verdict: "major_revisions",
    passed: false,
    contract_violations: [{ code: "ABSTRACT_WORDS", severity: "error", message: "Too long", expected: "250", actual: "312" }],
  },
  findings: [
    { finding_id: "n", severity: "note", category: "style", evidence: "e", recommendation: "" },
    { finding_id: "m", severity: "minor", category: "citations", evidence: "e", recommendation: "r" },
    { finding_id: "b", severity: "minor", category: "prisma", evidence: "e", recommendation: "r", blocking: true },
  ],
  audit_summary: null,
}

describe("auditItemsFromPayload", () => {
  it("orders failures, then warnings, then notes", () => {
    const items = auditItemsFromPayload(payload)
    expect(items.map((i) => [i.kind, i.id.startsWith("contract") ? "contract" : i.id])).toEqual([
      ["failure", "contract"],
      ["failure", "b"],
      ["warning", "m"],
      ["note", "n"],
    ])
    expect(items[0].detail).toBe("Too long · Expected 250 · got 312")
    expect(items[1].severityLabel).toBe("blocking")
  })

  it("handles empty payloads", () => {
    expect(auditItemsFromPayload(null)).toEqual([])
    expect(auditItemsFromPayload({ ...payload, latest_run: null, findings: [] })).toEqual([])
  })
})

describe("splitAuditSummary", () => {
  it("splits reviewer segments and humanizes their keys", () => {
    const parts = splitAuditSummary("general_systematic_review/balanced_overview: First part. | general_systematic_review/critical_sections: Second part.")
    expect(parts).toEqual([
      { title: "Balanced overview", body: "First part." },
      { title: "Critical sections", body: "Second part." },
    ])
  })
  it("keeps plain text without a key", () => {
    expect(splitAuditSummary("Just a summary.")).toEqual([{ title: null, body: "Just a summary." }])
  })
})
