// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { DollarSign } from "lucide-react"
import { StatTile } from "./stat-tile"

describe("StatTile", () => {
  it("renders label, value and sub-line", () => {
    render(<StatTile icon={DollarSign} label="Total cost" value="$12.34" sub="3 runs" />)
    expect(screen.getByText("Total cost")).toBeInTheDocument()
    expect(screen.getByText("$12.34")).toBeInTheDocument()
    expect(screen.getByText("3 runs")).toBeInTheDocument()
  })

  it("truncates the value with tabular numerals on a glass surface", () => {
    const { container } = render(<StatTile label="Papers" value="1,716" />)
    const value = screen.getByText("1,716")
    expect(value).toHaveClass("min-w-0", "truncate", "tabular-nums")
    expect(value).toHaveAttribute("title", "1,716")
    expect(container.firstChild).toHaveClass("glass-panel", "min-w-0")
  })

  it("omits the sub-line when not provided", () => {
    const { container } = render(<StatTile label="Papers" value={42} />)
    expect(container.querySelectorAll(".label-muted")).toHaveLength(0)
  })
})
