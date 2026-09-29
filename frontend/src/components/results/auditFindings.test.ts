import { describe, expect, it } from "vitest"
import {
  auditGateCountLine,
  auditGates,
  auditItemsFromPayload,
  contractCheckTitle,
  contractGateCountLine,
  formatExpectation,
  gateOverviewLine,
  plainAuditText,
  verdictBadgeVariant,
  humanizeGateReason,
  splitAuditSummary,
  type ManuscriptAuditPayload,
} from "./auditFindings"

describe("humanizeGateReason", () => {
  it("rewrites contract gate failures", () => {
    expect(humanizeGateReason("contract gate failed in mode=strict with 3 violation(s)")).toBe(
      "Consistency checks failed: 3 violations",
    )
    expect(humanizeGateReason("contract gate failed in mode=advisory with 1 violation(s)")).toBe(
      "Consistency checks failed: 1 violation",
    )
  })

  it("rewrites audit gate failures", () => {
    expect(humanizeGateReason("audit gate failed in mode=strict (verdict=major_revisions, blocking=8)")).toBe(
      "Audit verdict: major revisions (8 blocking issues)",
    )
    expect(humanizeGateReason("audit gate failed in mode=needs_revision (verdict=minor_revisions, blocking=1)")).toBe(
      "Audit verdict: minor revisions (1 blocking issue)",
    )
  })

  it("returns unknown reasons unchanged", () => {
    expect(humanizeGateReason("citation lineage gate failed")).toBe("citation lineage gate failed")
  })
})

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

describe("audit gates", () => {
  const wf1: ManuscriptAuditPayload = {
    ...payload,
    latest_run: {
      audit_run_id: "a1",
      verdict: "major_revisions",
      passed: false,
      contract_passed: false,
      contract_violations: [
        { code: "INCLUDED_COUNT_MISMATCH", severity: "error", message: "m", expected: "6", actual: "4" },
        { code: "DOMAIN_SCOPE_DRIFT", severity: "warning", message: "m" },
        { code: "ABSTRACT_UNDER_MINIMUM", severity: "error", message: "m" },
      ],
    },
    findings: [
      { finding_id: "b1", severity: "major", category: "c", evidence: "e", recommendation: "", blocking: true },
      { finding_id: "b2", severity: "major", category: "c", evidence: "e", recommendation: "", blocking: true },
      { finding_id: "m1", severity: "major", category: "c", evidence: "e", recommendation: "" },
      { finding_id: "n1", severity: "minor", category: "c", evidence: "e", recommendation: "" },
      { finding_id: "x1", severity: "note", category: "c", evidence: "e", recommendation: "" },
    ],
  }

  it("counts each gate from exactly the items it lists", () => {
    const gates = auditGates(wf1)!
    expect(gates.contract.items).toHaveLength(3)
    expect(contractGateCountLine(gates.contract)).toBe("3 violations · 2 errors · 1 warning")
    expect(gates.audit.items).toHaveLength(5)
    expect(auditGateCountLine(gates.audit)).toBe("5 findings · 2 blocking · 1 major · 1 minor · 1 note")
    expect(gates.audit.blocking + gates.audit.major + gates.audit.minor + gates.audit.notes).toBe(gates.audit.items.length)
  })

  it("titles contract checks in plain language", () => {
    const gates = auditGates(wf1)!
    expect(gates.contract.items.map((i) => i.title)).toEqual([
      "Study table count differs from included studies",
      "Abstract is too short",
      "Out-of-scope topics mentioned",
    ])
    expect(contractCheckTitle("SOME_NEW_CODE")).toBe("Some new code")
  })

  it("says in one line when pre-writing passed but the final checks did not", () => {
    const gates = auditGates(wf1)
    expect(gateOverviewLine("passed", gates)).toBe(
      "Pre-writing validation passed, but after writing the consistency checks failed and the manuscript audit returned major revisions.",
    )
    expect(gateOverviewLine("failed", gates)).toBeNull()
    expect(gateOverviewLine("passed", null)).toBeNull()
  })
})

describe("plainAuditText", () => {
  it("renders Python list literals as plain lists", () => {
    expect(plainAuditText("got ['tennis', 'badminton', \"table tennis\"]")).toBe("got tennis, badminton, table tennis")
  })

  it("replaces pipeline jargon and known check codes", () => {
    expect(plainAuditText("Row count disagrees with canonical synthesis cohort.")).toBe(
      "Row count disagrees with included studies.",
    )
    expect(plainAuditText("Reconcile the table with the canonical synthesis cohort of 6 studies")).toBe(
      "Reconcile the table with the 6 included studies",
    )
    expect(plainAuditText("The deterministic contract also flags INCLUDED_COUNT_MISMATCH (expected 6)")).toBe(
      'The consistency checks also flag "Study table count differs from included studies" (expected 6)',
    )
    expect(plainAuditText("Unknown CODE_NAME stays")).toBe("Unknown CODE_NAME stays")
  })
})

describe("verdictBadgeVariant", () => {
  it("maps verdicts to one tone", () => {
    expect(verdictBadgeVariant("major_revisions")).toBe("danger")
    expect(verdictBadgeVariant("minor_revisions")).toBe("warning")
    expect(verdictBadgeVariant("accept", true)).toBe("success")
    expect(verdictBadgeVariant("", false)).toBe("neutral")
  })
})

describe("formatExpectation", () => {
  it("spells out comparison operators", () => {
    expect(formatExpectation(">= 210", "ABSTRACT_UNDER_MINIMUM")).toBe("at least 210 words")
    expect(formatExpectation("<= 250", "ABSTRACT_OVER_LIMIT")).toBe("at most 250 words")
    expect(formatExpectation("<= 50% non-substantive key findings")).toBe("at most 50% non-substantive key findings")
    expect(formatExpectation(">= 1 grade_assessments row")).toBe("at least 1 grade_assessments row")
    expect(formatExpectation("> 3")).toBe("more than 3")
    expect(formatExpectation("< 3")).toBe("fewer than 3")
    expect(formatExpectation("== 6")).toBe("exactly 6")
    expect(formatExpectation("!= 0")).toBe("not 0")
    expect(formatExpectation("6")).toBe("6")
  })

  it("renders contract violation details without raw operators", () => {
    const items = auditItemsFromPayload({
      latest_run: {
        contract_violations: [
          { code: "ABSTRACT_UNDER_MINIMUM", severity: "error", message: "Short", expected: ">= 210", actual: "77" },
        ],
      },
      findings: [],
    } as unknown as Parameters<typeof auditItemsFromPayload>[0])
    expect(items[0].detail).toBe("Short · Expected at least 210 words · got 77")
  })
})
