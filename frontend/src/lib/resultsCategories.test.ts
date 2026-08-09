import { describe, expect, it } from "vitest"
import {
  buildResultsCategoryIds,
  defaultResultsCategory,
  resolveActiveResultsCategory,
  RESULTS_CATEGORY_ORDER,
  SUBMISSION_FOCUS_RESULTS_CATEGORY,
} from "./resultsCategories"

describe("resultsCategories", () => {
  it("orders categories manuscript → figures → quality → files → references when all visible", () => {
    const ids = buildResultsCategoryIds({
      hasManuscript: true,
      hasFiguresSection: true,
      hasExportRunId: true,
    })
    expect(ids).toEqual(["manuscript", "figures", "quality", "files", "references"])
  })

  it("always includes files and references", () => {
    expect(
      buildResultsCategoryIds({
        hasManuscript: false,
        hasFiguresSection: false,
        hasExportRunId: false,
      }),
    ).toEqual(["files", "references"])
  })

  it("omits manuscript and figures when not present", () => {
    expect(
      buildResultsCategoryIds({
        hasManuscript: false,
        hasFiguresSection: false,
        hasExportRunId: true,
      }),
    ).toEqual(["quality", "files", "references"])
  })

  it("defaults to manuscript when present", () => {
    expect(defaultResultsCategory(true)).toBe("manuscript")
    expect(defaultResultsCategory(false)).toBe("files")
  })

  it("resolves invalid active category to first available", () => {
    const available = buildResultsCategoryIds({
      hasManuscript: false,
      hasFiguresSection: false,
      hasExportRunId: false,
    })
    expect(resolveActiveResultsCategory("manuscript", available)).toBe("files")
    expect(resolveActiveResultsCategory("files", available)).toBe("files")
  })

  it("falls back to files when no categories available", () => {
    expect(resolveActiveResultsCategory("quality", [])).toBe("files")
  })

  it("maps submission focus to files category", () => {
    expect(SUBMISSION_FOCUS_RESULTS_CATEGORY).toBe("files")
  })

  it("RESULTS_CATEGORY_ORDER covers every ResultsCategory id", () => {
    const allFromBuilder = buildResultsCategoryIds({
      hasManuscript: true,
      hasFiguresSection: true,
      hasExportRunId: true,
    })
    for (const id of allFromBuilder) {
      expect(RESULTS_CATEGORY_ORDER).toContain(id)
    }
  })
})
