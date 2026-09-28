// @vitest-environment jsdom
import "@/test/dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { SetupView } from "./SetupView"

const envStatus = vi.hoisted(() => ({
  value: {
    required_ui_keys: ["fireworks"],
    providers: { fireworks: { configured: true, masked: "***", source: "env", required: true } },
    server_ready: true,
  } as unknown,
}))

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>()
  return {
    ...actual,
    fetchEnvKeysStatus: vi.fn(async () => envStatus.value),
    fetchRequiredLlmUiKeys: vi.fn(async () => ["fireworks"]),
    loadApiKeys: vi.fn(() => null),
  }
})

vi.mock("@/hooks/useHistory", () => ({
  useHistory: () => ({ data: [], error: null }),
}))

vi.mock("@/components/SettingsDialog", () => ({
  SettingsDialog: ({ open }: { open: boolean }) => (open ? <div role="dialog">settings-keys</div> : null),
}))

function renderSetup(onGenerateDraft = vi.fn()) {
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <SetupView
        defaultReviewYaml="research_question: x"
        onGenerateDraft={onGenerateDraft}
        onOpenDraftWithYaml={vi.fn()}
        disabled={false}
      />
    </QueryClientProvider>,
  )
  return onGenerateDraft
}

function precedes(a: HTMLElement, b: HTMLElement) {
  return Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)
}

describe("SetupView", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    )
    Element.prototype.scrollIntoView = vi.fn()
    envStatus.value = {
      required_ui_keys: ["fireworks"],
      providers: { fireworks: { configured: true, masked: "***", source: "env", required: true } },
      server_ready: true,
    }
  })

  it("orders heading, question, review type, options, then the primary CTA", () => {
    renderSetup()
    const heading = screen.getByRole("heading", { level: 1, name: "New review" })
    const question = screen.getByRole("textbox", { name: "Research question" })
    const systematic = screen.getByRole("radio", { name: /Systematic review/ })
    const healthSdg = screen.getByRole("checkbox", { name: /Health \+ SDG alignment/ })
    const reuse = screen.getByRole("button", { name: /Reuse past config/ })
    const cta = screen.getByRole("button", { name: "Generate config" })
    expect(precedes(heading, question)).toBe(true)
    expect(precedes(question, systematic)).toBe(true)
    expect(precedes(systematic, healthSdg)).toBe(true)
    expect(precedes(healthSdg, reuse)).toBe(true)
    expect(precedes(reuse, cta)).toBe(true)
  })

  it("requires a question and a review type before generating", async () => {
    const user = userEvent.setup()
    const onGenerate = renderSetup()
    const cta = screen.getByRole("button", { name: "Generate config" })
    expect(cta).toBeDisabled()
    await user.type(screen.getByRole("textbox", { name: "Research question" }), "Does X help Y?")
    expect(cta).toBeDisabled()
    expect(screen.getByText("Choose a review type to continue.")).toBeInTheDocument()
    await user.click(screen.getByRole("radio", { name: /Scoping review/ }))
    await user.click(cta)
    expect(onGenerate).toHaveBeenCalledWith(
      expect.objectContaining({ question: "Does X help Y?", reviewType: "scoping", questionFramework: "PCC" }),
    )
  })

  it("opens the decision guide from Help me decide and applies its result", async () => {
    const user = userEvent.setup()
    renderSetup()
    await user.click(screen.getByRole("button", { name: "Help me decide" }))
    expect(screen.getByText("Step 1 of up to 3")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Yes" }))
    await user.click(screen.getByRole("button", { name: "Yes" }))
    expect(screen.getByRole("radio", { name: /Scoping review/ })).toBeChecked()
  })

  it("names the missing provider up front and links to Settings keys", async () => {
    envStatus.value = {
      required_ui_keys: ["fireworks"],
      providers: { fireworks: { configured: false, masked: "", source: null, required: true } },
      server_ready: false,
    }
    const user = userEvent.setup()
    renderSetup()
    expect(await screen.findByText(/Missing API key: Fireworks AI/)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Open Settings → Keys" }))
    expect(screen.getByRole("dialog")).toHaveTextContent("settings-keys")
  })

  it("shows the reuse control with an empty hint when there is no history", async () => {
    const user = userEvent.setup()
    renderSetup()
    await user.click(screen.getByRole("button", { name: /Reuse past config/ }))
    expect(await screen.findByText(/No past reviews yet/)).toBeInTheDocument()
    await user.keyboard("{Escape}")
    expect(screen.queryByText(/No past reviews yet/)).not.toBeInTheDocument()
  })
})
