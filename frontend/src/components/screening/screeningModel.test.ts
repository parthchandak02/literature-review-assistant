import { describe, expect, it } from "vitest"
import type { ScreenedPaper, ScreeningOverride } from "@/lib/api"
import {
  formatAuthorList,
  approvalSummaryText,
  buildRows,
  countFilterTabs,
  countFinalDecisions,
  humanizeDecidedBy,
  humanizeExclusionReason,
  thresholdsText,
  selectVisibleRows,
  summaryLine,
  UNCERTAIN_OUTCOME,
} from "./screeningModel"

function paper(overrides: Partial<ScreenedPaper> & { paper_id: string }): ScreenedPaper {
  return {
    title: overrides.paper_id,
    authors: "",
    year: 2024,
    source_database: "pubmed",
    doi: null,
    abstract: null,
    stage: "title_abstract",
    decision: "include",
    reason: null,
    confidence: 0.5,
    ...overrides,
  }
}

const ov = (paper_id: string, decision: "include" | "exclude"): [string, ScreeningOverride] => [
  paper_id,
  { paper_id, decision },
]

describe("buildRows", () => {
  it("keeps the first row per paper, uses final_decision and decodes entities", () => {
    const rows = buildRows([
      paper({ paper_id: "a", decision: "include", final_decision: "exclude", title: "Students&amp;apos; sleep" }),
      paper({ paper_id: "a", decision: "uncertain" }),
      paper({ paper_id: "b" }),
    ])
    expect(rows.map((r) => r.key)).toEqual(["a", "b"])
    expect(rows[0].paper.decision).toBe("exclude")
    expect(rows[0].title).toBe("Students' sleep")
  })
})

describe("humanizers", () => {
  it("labels who decided", () => {
    expect(humanizeDecidedBy("human_override")).toBe("Human override")
    expect(humanizeDecidedBy("adjudicator")).toBe("AI adjudicator")
    expect(humanizeDecidedBy("screening_reviewer_a")).toBe("AI reviewer A")
    expect(humanizeDecidedBy("keyword_filter")).toBe("Keyword filter")
    expect(humanizeDecidedBy(null)).toBe("")
  })

  it("humanises exclusion codes but keeps prose", () => {
    expect(humanizeExclusionReason("wrong_population")).toBe("Wrong population")
    expect(humanizeExclusionReason("Not an RCT; adults only")).toBe("Not an RCT; adults only")
  })

  it("explains thresholds when present", () => {
    expect(thresholdsText(null)).toBeNull()
    expect(thresholdsText({ include: 0.85, exclude: 0.8, source: "calibration" })).toBe(
      "Calibrated on this run: at title and abstract, the first AI reviewer's call stands when it is at least " +
        "85% confident to include or 80% confident to exclude. Anything less certain gets a second reviewer. " +
        "Full text is always double-reviewed.",
    )
    expect(thresholdsText({ include: 0.9, exclude: 0.7, source: "settings" })).toMatch(/^From settings:/)
  })
})

describe("counts", () => {
  const rows = buildRows([
    paper({ paper_id: "a", decision: "include" }),
    paper({ paper_id: "b", decision: "include" }),
    paper({ paper_id: "c", decision: "uncertain" }),
    paper({ paper_id: "d", decision: "uncertain" }),
  ])
  const overrides = new Map([ov("a", "exclude"), ov("c", "include")])

  it("counts final decisions with overrides applied", () => {
    expect(countFinalDecisions(rows, overrides)).toEqual({
      total: 4,
      include: 2,
      exclude: 1,
      uncertain: 1,
      overridden: 2,
    })
  })

  it("counts filter tabs by AI decision so rows stay put", () => {
    expect(countFilterTabs(rows, overrides)).toEqual({
      all: 4,
      include: 2,
      exclude: 0,
      uncertain: 2,
      overridden: 2,
    })
  })

  it("formats the summary line", () => {
    expect(summaryLine(countFinalDecisions(rows, overrides))).toBe(
      "4 papers · 2 include · 1 exclude · 1 uncertain · 2 overridden",
    )
  })
})

describe("selectVisibleRows", () => {
  const rows = buildRows([
    paper({ paper_id: "a", title: "Zebra study", authors: "Smith", confidence: 0.9 }),
    paper({ paper_id: "b", title: "Apple trial", authors: "Jones", confidence: 0.2, decision: "uncertain" }),
    paper({ paper_id: "c", title: "Mango cohort", authors: "Smith", confidence: null }),
  ])
  const base = { filter: "all" as const, search: "", sort: "confidence-asc" as const, filterBasis: new Map() }

  it("sorts by confidence ascending with unscored rows last", () => {
    expect(selectVisibleRows(rows, base).map((r) => r.key)).toEqual(["b", "a", "c"])
  })

  it("sorts by confidence descending with unknown confidence last", () => {
    expect(selectVisibleRows(rows, { ...base, sort: "confidence-desc" }).map((r) => r.key)).toEqual(["a", "b", "c"])
  })

  it("sorts by title", () => {
    expect(selectVisibleRows(rows, { ...base, sort: "title" }).map((r) => r.key)).toEqual(["b", "c", "a"])
  })

  it("filters by decision, overridden and title/author search", () => {
    expect(selectVisibleRows(rows, { ...base, filter: "uncertain" }).map((r) => r.key)).toEqual(["b"])
    expect(
      selectVisibleRows(rows, { ...base, filter: "overridden", filterBasis: new Map([ov("a", "exclude")]) }).map(
        (r) => r.key,
      ),
    ).toEqual(["a"])
    expect(selectVisibleRows(rows, { ...base, search: "smith" }).map((r) => r.key)).toEqual(["a", "c"])
    expect(selectVisibleRows(rows, { ...base, search: "APPLE" }).map((r) => r.key)).toEqual(["b"])
  })
})

describe("approvalSummaryText", () => {
  it("states counts, what happens to uncertain papers, and the cost", () => {
    const text = approvalSummaryText({ total: 10, include: 6, exclude: 1, uncertain: 3, overridden: 2 })
    expect(text).toBe(
      `6 included, 3 uncertain → ${UNCERTAIN_OUTCOME}, 1 excluded, 2 overrides will be applied. ` +
        "Extraction will start and incur model cost.",
    )
  })

  it("handles singular and zero overrides", () => {
    expect(approvalSummaryText({ total: 1, include: 1, exclude: 0, uncertain: 0, overridden: 1 })).toContain(
      "1 override will be applied",
    )
    expect(approvalSummaryText({ total: 1, include: 1, exclude: 0, uncertain: 0, overridden: 0 })).toContain(
      "no overrides",
    )
  })
})

describe("formatAuthorList", () => {
  it("joins JSON array author strings and decodes unicode escapes", () => {
    expect(formatAuthorList('["Nguy\\u1ec5n Ch\\u00e2u", "Sara L. Terrell"]')).toBe("Nguyễn Châu, Sara L. Terrell")
  })
  it("keeps plain author text", () => {
    expect(formatAuthorList("Jae-ok Koh, Rod Cross")).toBe("Jae-ok Koh, Rod Cross")
  })
  it("returns malformed JSON-looking text unchanged", () => {
    expect(formatAuthorList("[unclosed")).toBe("[unclosed")
  })
})
