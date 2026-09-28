import { describe, expect, it } from "vitest"
import { isProsperoRegistrationComplete, parseProsperoFromYaml, prosperoIdError } from "./prosperoConfig"

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

describe("prosperoIdError", () => {
  it("accepts CRD42 plus digits in any case", () => {
    expect(prosperoIdError("CRD42025678901")).toBeNull()
    expect(prosperoIdError(" crd42025678901 ")).toBeNull()
  })

  it("explains each invalid shape", () => {
    expect(prosperoIdError("")).toBe("Enter your PROSPERO ID.")
    expect(prosperoIdError("42025678901")).toMatch(/start with CRD42/)
    expect(prosperoIdError("CRD-42025678901")).toMatch(/digits only/)
    expect(prosperoIdError("CRD4202")).toMatch(/too short/)
  })
})
