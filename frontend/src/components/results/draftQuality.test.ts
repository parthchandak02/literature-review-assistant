import { describe, expect, it } from "vitest"
import { detectTemplateText } from "./draftQuality"

const ids = (md: string) => detectTemplateText(md).map((m) => m.id)

describe("detectTemplateText", () => {
  it("returns nothing for clean prose", () => {
    expect(detectTemplateText("")).toEqual([])
    expect(detectTemplateText(null)).toEqual([])
    expect(
      ids("## Abstract\n\nWe searched MEDLINE and Embase for trials of exercise in adults. Does it help? Yes."),
    ).toEqual([])
  })

  it("flags the known template phrases", () => {
    expect(ids("Bibliographic databases were searched using the configured protocol and settings.")).toEqual([
      "configured-protocol",
    ])
    expect(ids("Studies for the topic were screened.")).toEqual(["for-the-topic"])
    expect(ids("Evidence synthesis was generated from 6 studies.")).toEqual(["synthesis-generated"])
    expect(ids("[TODO] add limitations")).toEqual(["placeholder-token"])
    expect(ids("Effect was {{effect_size}}.")).toEqual(["placeholder-token"])
  })

  it("flags a question pasted into a sentence once", () => {
    const found = detectTemplateText("This review evaluated What are the effects of X on Y?. Results follow.")
    expect(found).toHaveLength(1)
    expect(found[0].label).toBe("Question pasted into a sentence")
    expect(found[0].excerpt).toContain("?.")
  })

  it("ignores code spans and blocks", () => {
    expect(ids("Run `for the topic` in code.\n\n```\n{{x}}\n```")).toEqual([])
  })

  it("keeps excerpts short", () => {
    const long = `${"a ".repeat(200)}for the topic${" b".repeat(200)}`
    const [m] = detectTemplateText(long)
    expect(m.excerpt.length).toBeLessThan(110)
    expect(m.excerpt.startsWith("…")).toBe(true)
  })
})
