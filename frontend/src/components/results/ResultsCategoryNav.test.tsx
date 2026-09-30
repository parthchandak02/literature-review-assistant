// @vitest-environment jsdom
import "@/test/dom"
import { useState } from "react"
import { describe, expect, it } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import { BookOpen, FileText, FolderOpen, Image, ShieldCheck } from "lucide-react"
import { ResultsCategoryNav, type ResultsCategory, type ResultsCategoryItem } from "./ResultsCategoryNav"

const ITEMS: ResultsCategoryItem[] = [
  { id: "manuscript", label: "Manuscript", icon: FileText },
  { id: "figures", label: "Figures", icon: Image },
  { id: "quality", label: "Quality", icon: ShieldCheck },
  { id: "files", label: "Files", icon: FolderOpen },
  { id: "references", label: "References", icon: BookOpen },
]

function Harness({ initial = "manuscript" as ResultsCategory }) {
  const [active, setActive] = useState<ResultsCategory>(initial)
  return <ResultsCategoryNav items={ITEMS} activeCategory={active} onCategoryChange={setActive} />
}

describe("ResultsCategoryNav", () => {
  it("renders every category as a tab wired to its panel", () => {
    render(<Harness />)
    const tabs = screen.getAllByRole("tab")
    expect(tabs.map((t) => t.textContent)).toEqual(ITEMS.map((i) => i.label))
    for (const [index, tab] of tabs.entries()) {
      expect(tab).toHaveAttribute("aria-controls", `tabpanel-${ITEMS[index].id}`)
    }
    expect(screen.getByRole("tab", { name: "Manuscript" })).toHaveAttribute("aria-selected", "true")
  })

  it("lays tabs out as equal columns below sm instead of a scroll strip", () => {
    render(<Harness />)
    const list = screen.getByRole("tablist")
    expect(list.className).toContain("max-sm:grid")
    expect(list.className).toContain("max-sm:auto-cols-fr")
    expect(list.className).toContain("max-sm:[&>[role=tab]]:min-h-11")
  })

  it("selects on click and moves with arrow keys", () => {
    render(<Harness />)
    fireEvent.click(screen.getByRole("tab", { name: "References" }))
    expect(screen.getByRole("tab", { name: "References" })).toHaveAttribute("aria-selected", "true")

    fireEvent.keyDown(screen.getByRole("tablist"), { key: "ArrowRight" })
    expect(screen.getByRole("tab", { name: "Manuscript" })).toHaveAttribute("aria-selected", "true")
    fireEvent.keyDown(screen.getByRole("tablist"), { key: "ArrowLeft" })
    expect(screen.getByRole("tab", { name: "References" })).toHaveAttribute("aria-selected", "true")
    expect(screen.getByRole("tab", { name: "References" })).toHaveAttribute("tabindex", "0")
  })

  it("renders nothing with a single category", () => {
    const { container } = render(
      <ResultsCategoryNav items={ITEMS.slice(0, 1)} activeCategory="manuscript" onCategoryChange={() => {}} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
