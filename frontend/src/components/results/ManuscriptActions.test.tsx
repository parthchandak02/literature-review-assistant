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

const manuscript = { content: "# Title\n\n## Abstract\n\nClean prose.\n" }
const apiFetch = vi.fn(async (path: string) => {
  if (path.endsWith("/manuscript")) return manuscript
  throw new Error(`unexpected ${path}`)
})

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>()
  return {
    ...actual,
    apiFetch: (path: string) => apiFetch(path),
    triggerExport: (...args: unknown[]) => triggerExport(...args),
  }
})

const TEMPLATE_MD =
  "# Title\n\n## Abstract\n\nDatabases were searched using the configured protocol.\n\n## Methods\n\nFine.\n"

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
    apiFetch.mockClear()
    manuscript.content = "# Title\n\n## Abstract\n\nClean prose.\n"
  })

  it("does not auto-build on mount and builds on explicit click", async () => {
    const user = userEvent.setup()
    render(<ManuscriptActions docxPath={null} canExport exportRunId="run-1" allOutputs={{}} />)
    expect(triggerExport).not.toHaveBeenCalled()
    await user.click(screen.getByRole("button", { name: /Build submission package/ }))
    expect(apiFetch).toHaveBeenCalledWith("/run/run-1/manuscript")
    expect(screen.queryByRole("dialog")).toBeNull()
    expect(triggerExport).toHaveBeenCalledWith("run-1", false)
    expect(await screen.findByRole("link", { name: /Submission package/ })).toBeInTheDocument()
  })

  it("asks before rebuilding an existing package", async () => {
    const user = userEvent.setup()
    render(<ManuscriptActions docxPath={null} canExport exportRunId="run-2" allOutputs={completeOutputs} />)
    await user.click(await screen.findByRole("button", { name: "Rebuild submission package" }))
    expect(triggerExport).not.toHaveBeenCalled()
    expect(await screen.findByRole("dialog")).toHaveTextContent(/overwrites the existing package ZIP/)
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

  it("warns about template text before building and lets the user cancel", async () => {
    manuscript.content = TEMPLATE_MD
    const user = userEvent.setup()
    render(<ManuscriptActions docxPath={null} canExport exportRunId="run-4" allOutputs={{}} />)
    await user.click(screen.getByRole("button", { name: /Build submission package/ }))
    const dialog = await screen.findByRole("dialog")
    expect(dialog).toHaveTextContent("The manuscript still contains template text in: Abstract. Package anyway?")
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    expect(triggerExport).not.toHaveBeenCalled()
    expect(screen.queryByRole("dialog")).toBeNull()

    await user.click(screen.getByRole("button", { name: /Build submission package/ }))
    await user.click(await screen.findByRole("button", { name: "Package anyway" }))
    expect(triggerExport).toHaveBeenCalledWith("run-4", false)
  })

  it("combines the overwrite and template warnings on rebuild", async () => {
    manuscript.content = TEMPLATE_MD
    const user = userEvent.setup()
    render(<ManuscriptActions docxPath={null} canExport exportRunId="run-5" allOutputs={completeOutputs} />)
    await user.click(await screen.findByRole("button", { name: "Rebuild submission package" }))
    const dialog = await screen.findByRole("dialog")
    expect(dialog).toHaveTextContent(/overwrites the existing package ZIP/)
    expect(dialog).toHaveTextContent(/template text in: Abstract/)
    await user.click(screen.getByRole("button", { name: "Package anyway" }))
    expect(triggerExport).toHaveBeenCalledWith("run-5", true)
  })

  it("guards the chrome button too, and downloads a ready package without asking", async () => {
    manuscript.content = TEMPLATE_MD
    const user = userEvent.setup()
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {})
    render(<SubmissionPackageButton runId="run-6" />)
    await user.click(screen.getByRole("button", { name: /Download submission package/ }))
    expect(await screen.findByRole("dialog")).toHaveTextContent(/template text in: Abstract/)
    expect(triggerExport).not.toHaveBeenCalled()
    await user.click(screen.getByRole("button", { name: "Package anyway" }))
    expect(triggerExport).toHaveBeenCalledWith("run-6", false)
    await vi.waitFor(() => expect(click).toHaveBeenCalledTimes(1))

    apiFetch.mockClear()
    await user.click(screen.getByRole("button", { name: /Download submission package/ }))
    expect(apiFetch).not.toHaveBeenCalled()
    expect(screen.queryByRole("dialog")).toBeNull()
    expect(click).toHaveBeenCalledTimes(2)
    click.mockRestore()
  })
})
