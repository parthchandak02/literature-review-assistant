// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ApiKeysPanel } from "./ApiKeysSection"
import type { EnvKeysStatus } from "@/lib/api"

let status: EnvKeysStatus = {
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

async function openOptional() {
  await userEvent.click(screen.getByRole("button", { name: /Optional providers/ }))
}

describe("ApiKeysPanel", () => {
  it("shows server-configured keys without copying them into the browser", async () => {
    const onValidityChange = vi.fn()
    render(<ApiKeysPanel onValidityChange={onValidityChange} />)

    expect(await screen.findByText("Configured on server")).toBeInTheDocument()
    const fireworks = screen.getByLabelText(/^Fireworks AI/, { selector: "input" })
    expect(fireworks).toHaveValue("")
    expect(fireworks).toHaveAccessibleDescription(/^Using server key \(\*\*\*\*abcd\)/)
    expect(screen.getByText("****abcd", { selector: "code" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Show Fireworks AI" })).not.toBeInTheDocument()

    expect(screen.queryByLabelText("Gemini", { selector: "input" })).not.toBeInTheDocument()
    await openOptional()
    expect(screen.getByLabelText("Gemini", { selector: "input" })).toHaveAttribute("placeholder", "AIza...")

    expect(await screen.findByText(/All required keys configured/)).toBeInTheDocument()
    expect(screen.queryByText(/Using keys configured on the server/)).not.toBeInTheDocument()
    expect(screen.getByText(/All required keys configured/).textContent).not.toMatch(/Server \./)
    await waitFor(() => expect(onValidityChange).toHaveBeenLastCalledWith(true))
    expect(fetchEnvKeys).not.toHaveBeenCalled()
    expect(localStorage.length).toBe(0)
  })

  it("skips the prefix hint when the masked server key already shows it", async () => {
    const original = status
    status = {
      ...original,
      providers: {
        ...original.providers,
        gemini: { configured: true, masked: "AIza...uH54", source: "env", required: false },
      },
    }
    try {
      render(<ApiKeysPanel />)
      await screen.findAllByText("Configured on server")
      await openOptional()
      await waitFor(() =>
        expect(screen.getByLabelText("Gemini", { selector: "input" })).toHaveAccessibleDescription(
          "Using server key (AIza...uH54)",
        ),
      )
      expect(screen.getByText("fw_", { selector: "code" })).toBeInTheDocument()
      expect(screen.queryByText("AIza", { selector: "code" })).not.toBeInTheDocument()
    } finally {
      status = original
    }
  })

  it("validates the key format, clears a key and shows a saved indicator", async () => {
    render(<ApiKeysPanel />)
    const input = await screen.findByLabelText(/^Fireworks AI/, { selector: "input" })

    await userEvent.type(input, "bad")
    expect(input).toHaveAttribute("aria-invalid", "true")
    expect(screen.getByText('Fireworks AI keys usually start with "fw_".')).toBeInTheDocument()
    expect(await screen.findByText("Saved", {}, { timeout: 2000 })).toBeInTheDocument()

    await userEvent.click(screen.getByRole("button", { name: "Clear Fireworks AI" }))
    expect(input).toHaveValue("")
    expect(input).not.toHaveAttribute("aria-invalid")
    expect(screen.queryByRole("button", { name: "Clear Fireworks AI" })).not.toBeInTheDocument()
  })

  it("uses email inputs without a reveal toggle", async () => {
    render(<ApiKeysPanel />)
    await openOptional()
    const email = screen.getByLabelText("PubMed email", { selector: "input" })
    expect(email).toHaveAttribute("type", "email")
    expect(screen.queryByRole("button", { name: "Show PubMed API key" })).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText("PubMed API key", { selector: "input" }), "abc")
    await userEvent.type(email, "a@b.co")
    expect(screen.queryByRole("button", { name: "Show PubMed email" })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Show PubMed API key" })).toBeInTheDocument()
  })

  it("explains where a missing required key is used", async () => {
    status = {
      ...status,
      providers: { ...status.providers, fireworks: { configured: false, masked: "", source: null, required: true } },
    }
    render(<ApiKeysPanel />)
    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("Missing required key: Fireworks AI")
    expect(alert).toHaveTextContent(/used for screening, extraction/)
  })
})
