// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { Activity, DollarSign } from "lucide-react"
import { StatStrip, StatTile } from "./stat-tile"

describe("StatTile", () => {
  it("renders label, value and sub-line", () => {
    render(<StatTile icon={DollarSign} label="Total cost" value="$12.34" sub="3 runs" />)
    expect(screen.getByText("Total cost")).toBeInTheDocument()
    expect(screen.getByText("$12.34")).toBeInTheDocument()
    expect(screen.getByText("3 runs")).toBeInTheDocument()
  })

  it("truncates the value with mono tabular numerals on a glass surface", () => {
    const { container } = render(<StatTile label="Papers" value="1,716" />)
    const value = screen.getByText("1,716")
    expect(value).toHaveClass("num", "min-w-0", "truncate", "text-foreground")
    expect(value).toHaveAttribute("title", "1,716")
    expect(container.firstChild).toHaveClass("glass-panel", "min-w-0")
  })

  it("wraps the sub-line fully instead of clamping or truncating", () => {
    render(<StatTile label="Total cost" value="$1.20" sub="$0.2008 / included study · $0.7784 / 1k screened" />)
    const sub = screen.getByText(/included study/)
    expect(sub).not.toHaveClass("line-clamp-2")
    expect(sub).not.toHaveClass("truncate")
  })

  it("uses valueTitle as the hover text for a compact value", () => {
    render(<StatTile label="Tokens in" value="599.7K" valueTitle="599,747 tokens" />)
    expect(screen.getByText("599.7K")).toHaveAttribute("title", "599,747 tokens")
  })

  it("omits the sub-line when not provided", () => {
    const { container } = render(<StatTile label="Papers" value={42} />)
    expect(container.querySelectorAll(".label-muted")).toHaveLength(0)
  })

  it("applies the tone to the value and icon", () => {
    const { container } = render(<StatTile icon={Activity} label="LLM calls" value="1,204" tone="primary" />)
    expect(screen.getByText("1,204")).toHaveClass("text-intent-primary-text")
    expect(container.querySelector("svg")).toHaveClass("text-intent-primary-text")
  })

  it("keeps a neutral icon muted", () => {
    const { container } = render(<StatTile icon={DollarSign} label="Total cost" value="$1.20" />)
    expect(container.querySelector("svg")).toHaveClass("text-muted")
  })

  it("renders the inline variant without its own glass box", () => {
    const { container } = render(<StatTile variant="inline" label="Papers" value="12" />)
    expect(container.firstChild).not.toHaveClass("glass-panel")
    expect(container.firstChild).not.toHaveClass("border")
  })
})

describe("StatStrip", () => {
  it("holds inline tiles inside a single glass panel", () => {
    const { container } = render(
      <StatStrip>
        <StatTile variant="inline" label="Total cost" value="$1.20" />
        <StatTile variant="inline" label="LLM calls" value="12" />
      </StatStrip>,
    )
    expect(container.querySelectorAll(".glass-panel")).toHaveLength(1)
    const strip = container.firstChild as HTMLElement
    expect(strip).toHaveClass("glass-panel", "grid", "grid-cols-2")
    expect(strip.children).toHaveLength(2)
  })
})
