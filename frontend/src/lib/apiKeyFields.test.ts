import { describe, expect, it } from "vitest"
import { validateApiKeyValue } from "./apiKeyFields"

describe("validateApiKeyValue", () => {
  it("accepts empty values and keys with the expected prefix", () => {
    expect(validateApiKeyValue("fireworks", "")).toBeNull()
    expect(validateApiKeyValue("fireworks", "fw_abc123")).toBeNull()
    expect(validateApiKeyValue("gemini", "AIzaSyXYZ")).toBeNull()
    expect(validateApiKeyValue("anthropic", "sk-ant-api03-x")).toBeNull()
    expect(validateApiKeyValue("openai", "sk-proj-abc")).toBeNull()
  })

  it("flags keys with the wrong prefix", () => {
    expect(validateApiKeyValue("fireworks", "abc123")).toBe('Fireworks AI keys usually start with "fw_".')
    expect(validateApiKeyValue("groq", "sk-123")).toMatch(/gsk_/)
  })

  it("flags an Anthropic key pasted into the OpenAI field", () => {
    expect(validateApiKeyValue("openai", "sk-ant-api03-x")).toBe("This looks like an Anthropic key.")
  })

  it("rejects whitespace inside keys", () => {
    expect(validateApiKeyValue("scopus", "abc def")).toBe("Keys can't contain spaces.")
  })

  it("does not enforce a prefix for providers without a known format", () => {
    expect(validateApiKeyValue("mistral", "anything")).toBeNull()
    expect(validateApiKeyValue("scopus", "0123abcd")).toBeNull()
  })

  it("validates email fields", () => {
    expect(validateApiKeyValue("pubmedEmail", "me@example.com")).toBeNull()
    expect(validateApiKeyValue("crossrefEmail", "not-an-email")).toBe("Enter a valid email address.")
  })
})
