import { afterEach, describe, expect, it, vi } from "vitest"
import { APIResponseError, apiFetch } from "./client"

function mockFetch(status: number, body: string, contentType = "application/json") {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(body, { status, headers: { "Content-Type": contentType } })),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("apiFetch errors", () => {
  it("returns JSON on success", async () => {
    mockFetch(200, JSON.stringify({ ok: true }))
    await expect(apiFetch("/health")).resolves.toEqual({ ok: true })
  })

  it("includes a JSON detail string so the screen says why the request failed", async () => {
    mockFetch(404, JSON.stringify({ detail: "Run database not found" }))
    const error = await apiFetch("/run/abc/screening-summary").catch((err: unknown) => err)
    expect(error).toBeInstanceOf(APIResponseError)
    const responseError = error as APIResponseError
    expect(responseError.status).toBe(404)
    expect(responseError.detail).toEqual({ detail: "Run database not found" })
    expect(responseError.message).toBe(
      "Request failed: /run/abc/screening-summary: Run database not found",
    )
  })

  it("includes plain text when the body is not JSON", async () => {
    mockFetch(502, "upstream timed out", "text/plain")
    const error = await apiFetch("/db/abc/costs").catch((err: unknown) => err)
    expect(error).toBeInstanceOf(APIResponseError)
    expect((error as APIResponseError).message).toBe(
      "Request failed: /db/abc/costs: upstream timed out",
    )
    expect((error as APIResponseError).detail).toBe("upstream timed out")
  })

  it("summarizes field validation errors", async () => {
    mockFetch(
      422,
      JSON.stringify({
        detail: [
          { loc: ["body", "topic"], msg: "Field required", type: "missing" },
          { loc: ["body", "year"], msg: "Must be a number", type: "int_parsing" },
        ],
      }),
    )
    const error = await apiFetch("/runs").catch((err: unknown) => err)
    expect((error as APIResponseError).message).toBe(
      "Request failed: /runs: body.topic: Field required; body.year: Must be a number",
    )
  })

  it("keeps the path-only message when the body has no explanation", async () => {
    mockFetch(500, JSON.stringify({ ok: false }))
    const error = await apiFetch("/run/abc/manuscript").catch((err: unknown) => err)
    expect((error as APIResponseError).message).toBe("Request failed: /run/abc/manuscript")
  })

  it("does not paste an HTML error page into the message", async () => {
    mockFetch(502, "<html><body>Bad Gateway</body></html>", "text/html")
    const error = await apiFetch("/run/abc").catch((err: unknown) => err)
    expect(error).toBeInstanceOf(APIResponseError)
    expect((error as APIResponseError).message).toBe(
      "Request failed: /run/abc: the server sent a web page instead of data",
    )
    expect(String((error as APIResponseError).detail)).toContain("<html>")
  })

  it("clips a very long explanation", async () => {
    const reason = "x".repeat(300)
    mockFetch(500, JSON.stringify({ detail: reason }))
    const error = await apiFetch("/run/abc").catch((err: unknown) => err)
    const message = (error as APIResponseError).message
    expect(message.startsWith("Request failed: /run/abc: ")).toBe(true)
    expect(message.endsWith("...")).toBe(true)
    expect(message.length).toBe("Request failed: /run/abc: ".length + 240 + 3)
  })
})
