// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import { ApiKeysPanel } from "./ApiKeysSection"
import type { EnvKeysStatus } from "@/lib/api"

const status: EnvKeysStatus = {
  required_ui_keys: ["fireworks"],
  server_ready: true,
  providers: {
    fireworks: { configured: true, masked: "****abcd", source: "env", required: true },
    gemini: { configured: false, masked: "", source: null, required: false },
  },
}

const fetchEnvKeys = vi.fn(async () => ({}))

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>()
  return {
    ...actual,
    fetchEnvKeys: () => fetchEnvKeys(),
    fetchEnvKeysStatus: async () => status,
    fetchRequiredLlmUiKeys: async () => ["fireworks"],
  }
})

describe("ApiKeysPanel", () => {
  it("shows server-configured keys without copying them into the browser", async () => {
    const onValidityChange = vi.fn()
    render(<ApiKeysPanel onValidityChange={onValidityChange} />)

    expect(await screen.findByText("Configured on server")).toBeInTheDocument()
    const fireworks = screen.getByLabelText(/^Fireworks AI/, { selector: "input" })
    expect(fireworks).toHaveValue("")
    expect(fireworks).toHaveAttribute("placeholder", "Using server key (****abcd)")
    expect(screen.getByLabelText("Gemini", { selector: "input" })).toHaveAttribute("placeholder", "AIza...")

    expect(await screen.findByText(/All required keys configured/)).toBeInTheDocument()
    await waitFor(() => expect(onValidityChange).toHaveBeenLastCalledWith(true))
    expect(fetchEnvKeys).not.toHaveBeenCalled()
    expect(localStorage.length).toBe(0)
  })
})
