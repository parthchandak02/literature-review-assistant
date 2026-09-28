import { describe, expect, it } from "vitest"
import {
  decodeHtmlEntities,
  humanizeLogTag,
  humanizeSnake,
  humanizeStage,
  humanizeStatus,
  LOG_TAG_GLOSSARY,
  shortModelName,
} from "./humanize"

describe("humanizeSnake", () => {
  it("sentence-cases snake, kebab and camel identifiers", () => {
    expect(humanizeSnake("secondary_review")).toBe("Secondary review")
    expect(humanizeSnake("non-empirical")).toBe("Non empirical")
    expect(humanizeSnake("protocolOnly")).toBe("Protocol only")
    expect(humanizeSnake("  __double__underscore_ ")).toBe("Double underscore")
  })

  it("returns an empty string for empty input", () => {
    expect(humanizeSnake("")).toBe("")
    expect(humanizeSnake(null)).toBe("")
    expect(humanizeSnake(undefined)).toBe("")
  })
})

describe("humanizeStatus", () => {
  it("uses STATUS_LABEL for canonical and aliased statuses", () => {
    expect(humanizeStatus("completed")).toBe("Completed")
    expect(humanizeStatus("running")).toBe("Running")
    expect(humanizeStatus("stale")).toBe("Stale")
    expect(humanizeStatus("config_generating")).toBe("Generating config")
    expect(humanizeStatus("config_ready")).toBe("Config ready")
    expect(humanizeStatus("interrupted")).toBe("Cancelled")
    expect(humanizeStatus("idle")).toBe("Ready")
    expect(humanizeStatus(null)).toBe("Ready")
  })

  it("humanizes unknown statuses instead of calling them Ready", () => {
    expect(humanizeStatus("pending_upload")).toBe("Pending upload")
  })
})

describe("humanizeStage", () => {
  it("maps screening stage ids", () => {
    expect(humanizeStage("title_abstract")).toBe("Title and abstract")
    expect(humanizeStage("fulltext")).toBe("Full text")
    expect(humanizeStage("calibration")).toBe("Calibration")
    expect(humanizeStage("citation_chasing")).toBe("Citation chasing")
    expect(humanizeStage(undefined)).toBe("")
  })
})

describe("shortModelName", () => {
  it("strips the Fireworks account path and date suffix", () => {
    expect(shortModelName("accounts/fireworks/models/deepseek-v4-pro-0813")).toEqual({
      name: "deepseek-v4-pro",
      provider: "Fireworks",
    })
  })

  it("handles provider:model forms", () => {
    expect(shortModelName("fireworks:accounts/fireworks/models/glm-5p3")).toEqual({
      name: "glm-5p3",
      provider: "Fireworks",
    })
    expect(shortModelName("google-gla:gemini-2.5-flash")).toEqual({ name: "gemini-2.5-flash", provider: "Google" })
    expect(shortModelName("openrouter:anthropic/claude-sonnet-4")).toEqual({
      name: "claude-sonnet-4",
      provider: "OpenRouter",
    })
  })

  it("strips long date snapshots but keeps short version numbers", () => {
    expect(shortModelName("openai:gpt-4o-2024-08-06").name).toBe("gpt-4o")
    expect(shortModelName("anthropic:claude-3-5-sonnet-20241022").name).toBe("claude-3-5-sonnet")
    expect(shortModelName("google-vertex:gemini-1.5-pro-001").name).toBe("gemini-1.5-pro-001")
  })

  it("returns no provider for bare model ids and handles empty input", () => {
    expect(shortModelName("gpt-oss-120b")).toEqual({ name: "gpt-oss-120b", provider: null })
    expect(shortModelName("")).toEqual({ name: "", provider: null })
    expect(shortModelName(null)).toEqual({ name: "", provider: null })
  })

  it("humanizes unknown providers", () => {
    expect(shortModelName("my_lab:tiny-model").provider).toBe("My lab")
  })
})

describe("humanizeLogTag", () => {
  it("covers every tag emitted by logLine", () => {
    const tags = [
      "PHASE", "DONE", "PROG", "TIMER", "...", "CALIB", "LLM", "SEARCH", "SRCHOV", "INCLUDE", "EXCLUDE",
      "AUTO", "PDF", "EXTRACT", "SYNTH", "RATELIMIT", "DB", "ERROR", "CANCEL", "FUNNEL", "QA", "BATCH", "CAP",
    ]
    for (const tag of tags) {
      const info = humanizeLogTag(tag)
      expect(info.label, tag).not.toBe("")
      expect(info.description, tag).not.toBe("")
    }
    expect(Object.keys(LOG_TAG_GLOSSARY).sort()).toEqual([...tags].sort())
  })

  it("normalizes case, padding, brackets and dots", () => {
    expect(humanizeLogTag("  prog ").label).toBe("Progress")
    expect(humanizeLogTag("[AUTO]").label).toBe("Rule-based")
    expect(humanizeLogTag("[LLM]").label).toBe("AI call")
    expect(humanizeLogTag("....").label).toBe("Status")
  })

  it("falls back for unknown tags", () => {
    expect(humanizeLogTag("NEW_TAG")).toEqual({ label: "New tag", description: "" })
    expect(humanizeLogTag("")).toEqual({ label: "", description: "" })
  })
})

describe("decodeHtmlEntities", () => {
  it("decodes single and double-encoded entities", () => {
    expect(decodeHtmlEntities("students&apos;")).toBe("students'")
    expect(decodeHtmlEntities("students&amp;apos;")).toBe("students'")
    expect(decodeHtmlEntities("A &amp;amp;amp; B")).toBe("A & B")
    expect(decodeHtmlEntities("&lt;i&gt;in vitro&lt;/i&gt;")).toBe("<i>in vitro</i>")
  })

  it("decodes numeric entities", () => {
    expect(decodeHtmlEntities("it&#39;s")).toBe("it's")
    expect(decodeHtmlEntities("it&#x27;s")).toBe("it's")
    expect(decodeHtmlEntities("p &#8804; 0.05")).toBe("p ≤ 0.05")
  })

  it("respects case for Greek letters and leaves unknown entities alone", () => {
    expect(decodeHtmlEntities("&Delta; vs &delta;")).toBe("&Delta; vs δ")
    expect(decodeHtmlEntities("&AMP;")).toBe("&")
    expect(decodeHtmlEntities("&notarealentity; & plain")).toBe("&notarealentity; & plain")
    expect(decodeHtmlEntities("&#0; &#xFFFFFFF;")).toBe("&#0; &#xFFFFFFF;")
  })

  it("stops after maxPasses and handles empty input", () => {
    expect(decodeHtmlEntities("&amp;amp;lt;", 1)).toBe("&amp;lt;")
    expect(decodeHtmlEntities(null)).toBe("")
    expect(decodeHtmlEntities("no entities")).toBe("no entities")
  })
})
