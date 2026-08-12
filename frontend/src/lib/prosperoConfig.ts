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
