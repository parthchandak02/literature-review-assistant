import { describe, expect, it } from "vitest"
import { isProsperoRegistrationComplete, parseProsperoFromYaml } from "./prosperoConfig"

const SAMPLE_YAML = `
protocol:
  registered: true
  registry: PROSPERO
  registration_number: CRD42026123456
  registration_date: 2026-08-10
`

describe("parseProsperoFromYaml", () => {
  it("extracts registration fields from review yaml", () => {
    const parsed = parseProsperoFromYaml(SAMPLE_YAML)
    expect(parsed.registered).toBe(true)
    expect(parsed.registrationNumber).toBe("CRD42026123456")
    expect(parsed.registrationDate).toBe("2026-08-10")
  })

  it("treats valid saved registration as complete", () => {
    const parsed = parseProsperoFromYaml(SAMPLE_YAML)
    expect(isProsperoRegistrationComplete(parsed)).toBe(true)
  })

  it("treats missing registration as incomplete", () => {
    const parsed = parseProsperoFromYaml("protocol:\n  registered: false\n")
    expect(isProsperoRegistrationComplete(parsed)).toBe(false)
  })
})
