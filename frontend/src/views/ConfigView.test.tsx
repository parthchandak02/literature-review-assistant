// @vitest-environment jsdom
import "@/test/dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import { act, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ConfigView, type DraftConfigContext } from "./ConfigView"
import { setDraftYamlEdit } from "@/hooks/useDraftConfigFlow"

const GENERATED = "# Config generation mode: web grounded\nresearch_question: x\nreview_type: scoping\n"

function draft(overrides: Partial<DraftConfigContext> = {}): DraftConfigContext {
  return {
    request: { question: "x", reviewType: "scoping" },
    yaml: GENERATED,
    isGenerating: false,
    activeStep: "finalizing",
    stepMetadata: {},
    usedWebFallback: false,
    fallbackReason: null,
    generationError: null,
    ...overrides,
  }
}

function renderConfig(draftConfig: DraftConfigContext | null, onPrepareProspero = vi.fn()) {
  const client = new QueryClient()
  const view = (
    <QueryClientProvider client={client}>
      <ConfigView workflowId="wf-1" draftConfig={draftConfig} onPrepareProspero={onPrepareProspero} />
    </QueryClientProvider>
  )
  const result = render(view)
  return { ...result, view, onPrepareProspero }
}

afterEach(() => {
  act(() => setDraftYamlEdit(null))
})

describe("ConfigView draft editor", () => {
  it("tracks edits, keeps them across remounts, and resets to generated", async () => {
    const user = userEvent.setup()
    const { unmount, view } = renderConfig(draft())
    await user.click(screen.getByRole("button", { name: "Edit" }))
    const editor = screen.getByRole("textbox", { name: "Review config YAML" })
    fireEvent.change(editor, { target: { value: `${GENERATED}keywords: [a]\n` } })
    expect(screen.getByText("Unsaved edits")).toBeInTheDocument()

    unmount()
    render(view)
    expect(screen.getByText("Unsaved edits")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Reset to generated" }))
    expect(screen.queryByText("Unsaved edits")).not.toBeInTheDocument()
  })

  it("blocks the PROSPERO draft step on invalid YAML and shows the line", async () => {
    const user = userEvent.setup()
    const { onPrepareProspero } = renderConfig(draft())
    const prepare = screen.getByRole("button", { name: "Generate PROSPERO draft" })
    expect(prepare).toBeEnabled()

    await user.click(screen.getByRole("button", { name: "Edit" }))
    fireEvent.change(screen.getByRole("textbox", { name: "Review config YAML" }), {
      target: { value: "research_question: x\nkeywords:\n\t- a\n" },
    })
    expect(screen.getByRole("alert")).toHaveTextContent("YAML error on line 3")
    expect(prepare).toBeDisabled()
    expect(onPrepareProspero).not.toHaveBeenCalled()
  })

  it("uses PCC for scoping drafts and plain step labels", () => {
    renderConfig(draft())
    expect(screen.getByText("PCC")).toBeInTheDocument()
    expect(screen.queryByText("PICO")).not.toBeInTheDocument()
    expect(screen.getByText("Database routing")).toBeInTheDocument()
    expect(screen.queryByText("Backup")).not.toBeInTheDocument()
  })

  it("hides the stepper and allows launch for pasted configs", async () => {
    const user = userEvent.setup()
    const { onPrepareProspero } = renderConfig(draft({ request: null, yaml: "research_question: x\n" }))
    expect(screen.queryByText("Database routing")).not.toBeInTheDocument()
    expect(screen.getByText(/Pasted config/)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Generate PROSPERO draft" }))
    expect(onPrepareProspero).toHaveBeenCalledWith("research_question: x\n")
  })
})
