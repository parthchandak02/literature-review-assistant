// @vitest-environment jsdom
import "@/test/dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ManuscriptActions } from "./ManuscriptActions"
import { SubmissionPackageButton } from "./SubmissionPackageButton"
import { resetPackageStore } from "./submissionPackage"

const triggerExport = vi.fn<(...args: unknown[]) => Promise<{ files: string[] }>>(async () => ({
  files: ["/out/submission/manuscript.tex"],
}))

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>()
  return { ...actual, triggerExport: (...args: unknown[]) => triggerExport(...args) }
})

const completeOutputs = {
  submission: {
    tex: "/out/submission/manuscript.tex",
    docx: "/out/submission/manuscript.docx",
    bib: "/out/submission/references.bib",
  },
}

describe("ManuscriptActions", () => {
  beforeEach(() => {
    resetPackageStore()
    triggerExport.mockClear()
  })

  it("does not auto-build on mount and builds on explicit click", async () => {
    const user = userEvent.setup()
    render(<ManuscriptActions docxPath={null} canExport exportRunId="run-1" allOutputs={{}} />)
    expect(triggerExport).not.toHaveBeenCalled()
    await user.click(screen.getByRole("button", { name: /Build submission package/ }))
    expect(triggerExport).toHaveBeenCalledWith("run-1", false)
    expect(await screen.findByRole("link", { name: /Submission package/ })).toBeInTheDocument()
  })

  it("asks before rebuilding an existing package", async () => {
    const user = userEvent.setup()
    render(<ManuscriptActions docxPath={null} canExport exportRunId="run-2" allOutputs={completeOutputs} />)
    await user.click(await screen.findByRole("button", { name: "Rebuild submission package" }))
    expect(triggerExport).not.toHaveBeenCalled()
    expect(screen.getByRole("dialog")).toHaveTextContent(/overwrites the existing package ZIP/)
    await user.click(screen.getByRole("button", { name: "Rebuild" }))
    expect(triggerExport).toHaveBeenCalledWith("run-2", true)
  })

  it("shares state with the chrome button", async () => {
    const user = userEvent.setup()
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {})
    render(
      <>
        <SubmissionPackageButton runId="run-3" />
        <ManuscriptActions docxPath={null} canExport exportRunId="run-3" allOutputs={{}} />
      </>,
    )
    await user.click(screen.getByRole("button", { name: /Download submission package/ }))
    expect(await screen.findByRole("link", { name: /Submission package/ })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Build submission package/ })).toBeNull()
    click.mockRestore()
  })
})
