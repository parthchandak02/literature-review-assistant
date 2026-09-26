// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ManuscriptActions } from "./ManuscriptActions"

const triggerExport = vi.fn(async () => ({ files: ["/out/submission/manuscript.tex"] }))

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>()
  return { ...actual, triggerExport: (...args: unknown[]) => triggerExport(...(args as [])) }
})

describe("ManuscriptActions", () => {
  it("does not auto-export on mount and packages on explicit click", async () => {
    const user = userEvent.setup()
    render(
      <ManuscriptActions docxPath={null} canExport exportRunId="run-1" allOutputs={{}} />,
    )
    expect(triggerExport).not.toHaveBeenCalled()
    await user.click(screen.getByRole("button", { name: /Package manuscript/ }))
    expect(triggerExport).toHaveBeenCalledWith("run-1", false)
    expect(await screen.findByRole("link", { name: /Submission Package/ })).toBeInTheDocument()
  })
})
