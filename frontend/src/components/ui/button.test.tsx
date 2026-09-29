// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { Button, buttonVariants } from "./button"

describe("Button", () => {
  it("pairs outline-none with a visible focus ring", () => {
    render(<Button>Go</Button>)
    const cls = screen.getByRole("button", { name: "Go" }).className
    expect(cls).toContain("focus-visible:ring-2")
    expect(cls).toContain("focus-visible:ring-ring")
    expect(cls).toContain("focus-visible:ring-offset-2")
    expect(cls).toContain("rounded-control")
    expect(cls).not.toMatch(/(^|\s)outline-none(\s|$)/)
  })

  it("uses solid fill tokens for solid variants", () => {
    expect(buttonVariants({ variant: "default" })).toContain("bg-intent-primary-solid")
    expect(buttonVariants({ variant: "default" })).toContain("text-intent-primary-solid-fg")
    expect(buttonVariants({ variant: "destructive" })).toContain("bg-intent-danger-solid")
    expect(buttonVariants({ variant: "success" })).toContain("bg-intent-success-solid")
    expect(buttonVariants({ variant: "warning" })).toContain("text-intent-warning-solid-fg")
  })

  it.each(["default", "destructive", "success", "warning"] as const)(
    "disabled %s renders as an inert neutral surface, not a faded fill",
    (variant) => {
      render(
        <Button variant={variant} disabled>
          Start
        </Button>,
      )
      const button = screen.getByRole("button", { name: "Start" })
      expect(button).toBeDisabled()
      const cls = button.className.split(/\s+/)
      expect(cls).toEqual(
        expect.arrayContaining([
          "disabled:bg-surface-2",
          "disabled:text-muted",
          "disabled:border-border",
          "disabled:opacity-100",
          "disabled:pointer-events-none",
        ]),
      )
      expect(cls).not.toContain("disabled:opacity-50")
    },
  )

  it("keeps the faded disabled style for non-solid variants", () => {
    render(
      <Button variant="outline" disabled>
        Cancel
      </Button>,
    )
    const cls = screen.getByRole("button", { name: "Cancel" }).className.split(/\s+/)
    expect(cls).toContain("disabled:opacity-50")
    expect(cls).not.toContain("disabled:bg-surface-2")
  })

  it("passes aria-disabled through for focusable disabled buttons", () => {
    render(<Button aria-disabled="true">Soft</Button>)
    expect(screen.getByRole("button", { name: "Soft" })).toHaveAttribute("aria-disabled", "true")
  })

  it.each([
    ["xs", "h-7"],
    ["sm", "h-8"],
    ["default", "h-9"],
    ["lg", "h-10"],
    ["icon", "h-9"],
    ["icon-sm", "h-8"],
  ] as const)("size %s maps to %s", (size, height) => {
    const cls = buttonVariants({ size }).split(/\s+/)
    expect(cls).toContain(height)
  })

  it("icon sizes are square", () => {
    expect(buttonVariants({ size: "icon" }).split(/\s+/)).toContain("w-9")
    expect(buttonVariants({ size: "icon-sm" }).split(/\s+/)).toContain("w-8")
  })

  it("defaults to h-9", () => {
    render(<Button>Default</Button>)
    expect(screen.getByRole("button").className.split(/\s+/)).toContain("h-9")
  })
})
