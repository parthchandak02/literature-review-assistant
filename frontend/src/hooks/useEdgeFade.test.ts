import { describe, expect, it } from "vitest"
import { edgeFadeMask } from "./useEdgeFade"

describe("edgeFadeMask", () => {
  it("returns no mask when nothing overflows", () => {
    expect(edgeFadeMask({ start: false, end: false })).toBeUndefined()
  })

  it("fades only the edges that have hidden content", () => {
    expect(edgeFadeMask({ start: false, end: true })?.maskImage).toBe(
      "linear-gradient(to right, black, black calc(100% - 2rem), transparent)",
    )
    expect(edgeFadeMask({ start: true, end: false })?.maskImage).toBe(
      "linear-gradient(to right, transparent, black 2rem, black)",
    )
  })

  it("fades vertically for the y axis", () => {
    expect(edgeFadeMask({ start: false, end: true }, "y")?.maskImage).toBe(
      "linear-gradient(to bottom, black, black calc(100% - 2rem), transparent)",
    )
  })
})
