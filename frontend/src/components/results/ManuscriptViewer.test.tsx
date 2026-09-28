// @vitest-environment jsdom
import "@/test/dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ManuscriptViewer } from "./ManuscriptViewer"

let content = ""

vi.mock("@/hooks/useFilePreview", () => ({
  useFileTextPreview: () => ({ content, loading: false, error: null, retry: vi.fn() }),
}))

function renderViewer() {
  return render(
    <ManuscriptViewer
      filePath="runs/wf/doc_manuscript.md"
      docxPath={null}
      canExport={false}
      exportRunId={null}
      allOutputs={{}}
    />,
  )
}

describe("ManuscriptViewer", () => {
  beforeEach(() => {
    content = ""
  })

  it("renders a TOC rail from headings and hides Outline without headings", () => {
    content = "# Title\n\nBody\n\n## Methods\n\nText"
    const { unmount } = renderViewer()
    const nav = screen.getByRole("navigation", { name: "Manuscript outline" })
    expect(nav).toHaveTextContent("Methods")
    expect(screen.getByRole("button", { name: /Outline/ })).toBeInTheDocument()
    unmount()

    content = "Just a paragraph."
    renderViewer()
    expect(screen.queryByRole("navigation", { name: "Manuscript outline" })).toBeNull()
    expect(screen.queryByRole("button", { name: /Outline/ })).toBeNull()
  })

  it("labels zoom controls and resets on the percentage", async () => {
    const user = userEvent.setup()
    content = "Text"
    renderViewer()
    await user.click(screen.getByRole("button", { name: "Zoom in" }))
    expect(screen.getByRole("button", { name: /Zoom 115%/ })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /reset to 100%/ }))
    expect(screen.getByRole("button", { name: /Zoom 100%/ })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Zoom out" })).toBeInTheDocument()
  })

  it("shows the draft quality chip only for template text", () => {
    content = "## Abstract\n\nDatabases were searched using the configured protocol and settings."
    const { unmount } = renderViewer()
    expect(screen.getByRole("button", { name: /Draft quality/ })).toBeInTheDocument()
    unmount()
    content = "## Abstract\n\nWe searched MEDLINE."
    renderViewer()
    expect(screen.queryByRole("button", { name: /Draft quality/ })).toBeNull()
  })

  it("wraps tables and shows a placeholder for missing figures", () => {
    content = "| a | b |\n|---|---|\n| 1 | 2 |\n\n![Forest plot](fig.png)"
    const { container } = renderViewer()
    expect(container.querySelector(".overflow-x-auto > table")).not.toBeNull()
    fireEvent.error(screen.getByRole("img", { name: "Forest plot" }))
    expect(screen.getByRole("img", { name: "Figure not found: Forest plot" })).toBeInTheDocument()
  })
})
