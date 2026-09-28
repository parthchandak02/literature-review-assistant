import { parseDocument } from "yaml"
import type { ReviewTypeChoice } from "@/components/setup/types"

export interface YamlIssue {
  message: string
  line: number | null
}

export function validateReviewYaml(text: string): YamlIssue | null {
  if (!text.trim()) return { message: "Config is empty.", line: null }
  const doc = parseDocument(text)
  const [first] = doc.errors
  if (first) {
    const line = first.linePos?.[0]?.line ?? null
    const message = first.message.split("\n")[0].replace(/\s+at line \d+, column \d+:?$/, "")
    return { message, line }
  }
  const root = doc.toJS() as unknown
  if (root === null || typeof root !== "object" || Array.isArray(root)) {
    return { message: "Config must be a YAML mapping (key: value pairs).", line: null }
  }
  return null
}

export function reviewTypeFromYaml(text: string): ReviewTypeChoice | null {
  const match = text.match(/^review_type:\s*['"]?(\w+)['"]?/m)
  const value = match?.[1]?.toLowerCase()
  if (value === "scoping" || value === "systematic") return value
  return null
}
