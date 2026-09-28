import { isProsperoRegistrationNumberValid } from "@/lib/constants"

export interface ParsedProsperoConfig {
  registered: boolean
  registrationNumber: string
  registrationDate: string
}

export function parseProsperoFromYaml(yaml: string): ParsedProsperoConfig {
  const registered = /^[^\S\n]*registered:\s*true\s*$/im.test(yaml)
  const numberMatch = yaml.match(/registration_number:\s*['"]?([^'"\n#]+)['"]?/i)
  const dateMatch = yaml.match(/registration_date:\s*['"]?([^'"\n#]+)['"]?/i)
  return {
    registered,
    registrationNumber: numberMatch?.[1]?.trim() ?? "",
    registrationDate: dateMatch?.[1]?.trim() ?? "",
  }
}

export function isProsperoRegistrationComplete(config: ParsedProsperoConfig): boolean {
  return (
    config.registered &&
    isProsperoRegistrationNumberValid(config.registrationNumber) &&
    config.registrationDate.length > 0
  )
}

export const PROSPERO_ID_HELPER = "Format: CRD42 followed by digits, e.g. CRD42025678901."

export function prosperoIdError(value: string): string | null {
  const trimmed = value.trim()
  if (!trimmed) return "Enter your PROSPERO ID."
  if (!/^CRD/i.test(trimmed)) return "PROSPERO IDs start with CRD42."
  if (!/^CRD\d+$/i.test(trimmed)) return "Use CRD followed by digits only, with no spaces or dashes."
  if (!isProsperoRegistrationNumberValid(trimmed)) {
    return "That ID is too short. PROSPERO IDs have at least 9 digits after CRD."
  }
  return null
}

/** Backend `submit-prospero` has no "unregistered" mode yet; flip once it does. */
export const PROSPERO_SKIP_SUPPORTED = false
