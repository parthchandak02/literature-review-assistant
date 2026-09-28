import { describe, expect, it } from "vitest"
import { defaultUrlTransform } from "react-markdown"
import { safeUrlTransform } from "./manuscriptUtils"

describe("safeUrlTransform", () => {
  it.each([
    "https://example.org/a?b#c",
    "mailto:a@b.org",
    "figures/prisma.png",
    "#section",
    "javascript:alert(1)",
    "data:image/png;base64,AAAA",
    "?q=a:b",
  ])("matches react-markdown for %s", (url) => {
    expect(safeUrlTransform(url)).toBe(defaultUrlTransform(url))
  })
})
