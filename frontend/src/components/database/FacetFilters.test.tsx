// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { FacetMenu } from "./FacetFilters"
import { facetOptions } from "./facetOptions"
import { FilterChipBar } from "./FilterChipBar"
import { formatPValue, formatStat } from "./outcomeFormat"
import type { PapersFacets } from "@/lib/api/db"

const facets: PapersFacets = {
  years: [],
  sources: [],
  countries: [],
  ta_decisions: [],
  ft_decisions: [],
  primary_statuses: [],
  counts: {
    ta_decision: [
      { value: "include", count: 12 },
      { value: "exclude", count: 30 },
      { value: null, count: 4 },
    ],
  },
}

describe("facetOptions", () => {
  it("maps counts, humanises labels and maps null to the none sentinel", () => {
    expect(facetOptions("ta", facets, [])).toEqual([
      { value: "include", label: "Include", count: 12 },
      { value: "exclude", label: "Exclude", count: 30 },
      { value: "__none__", label: "Not screened", count: 4 },
    ])
  })

  it("keeps selected values that dropped to zero", () => {
    const opts = facetOptions("ta", facets, ["uncertain"])
    expect(opts.at(-1)).toEqual({ value: "uncertain", label: "Uncertain", count: 0 })
  })
})

describe("FacetMenu", () => {
  it("shows counts and toggles a value on select while staying open", async () => {
    const user = userEvent.setup()
    const onToggle = vi.fn()
    render(
      <FacetMenu
        facetKey="ta"
        label="Title/abstract"
        selected={["exclude"]}
        options={facetOptions("ta", facets, ["exclude"])}
        onToggle={onToggle}
        onClear={vi.fn()}
      />,
    )
    const trigger = screen.getByRole("button", { name: /title\/abstract/i })
    expect(trigger).toHaveTextContent("1")
    trigger.focus()
    await user.keyboard("{Enter}")
    const include = await screen.findByRole("menuitemcheckbox", { name: /include/i })
    expect(include).toHaveTextContent("12")
    expect(screen.getByRole("menuitemcheckbox", { name: /exclude/i })).toHaveAttribute(
      "aria-checked",
      "true",
    )
    await user.click(include)
    expect(onToggle).toHaveBeenCalledWith("include")
    expect(screen.getByRole("menu")).toBeInTheDocument()
  })
})

describe("FilterChipBar", () => {
  it("renders 24px remove targets", () => {
    render(
      <FilterChipBar
        filters={[{ id: "ta:include", label: "Title/abstract", value: "Include" }]}
        onRemove={vi.fn()}
        onClearAll={vi.fn()}
      />,
    )
    expect(screen.getByRole("button", { name: /remove title\/abstract filter/i })).toHaveClass("size-6")
  })
})

describe("outcome formatting", () => {
  it("formats p-values and stats", () => {
    expect(formatPValue(0.0004)).toBe("<0.001")
    expect(formatPValue(0.0321)).toBe("0.032")
    expect(formatPValue(null)).toBe("–")
    expect(formatStat(1.23456)).toBe("1.23")
    expect(formatStat(120)).toBe("120")
    expect(formatStat("n/a")).toBe("n/a")
  })
})
