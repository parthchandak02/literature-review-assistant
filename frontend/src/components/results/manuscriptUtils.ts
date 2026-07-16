import { defaultUrlTransform } from "react-markdown"
import { APIResponseError, downloadUrl } from "@/lib/api"

export function isFilePath(val: unknown): val is string {
  if (typeof val !== "string") return false
  const t = val.trim()
  return (
    t.startsWith("runs/") ||
    t.startsWith("data/") ||
    t.startsWith("./") ||
    t.startsWith("/")
  )
}

export function hasSubmissionArtifacts(obj: unknown): boolean {
  if (typeof obj === "string" && isFilePath(obj)) {
    return /\/submission\//.test(obj)
  }
  if (obj && typeof obj === "object" && !Array.isArray(obj)) {
    for (const value of Object.values(obj as Record<string, unknown>)) {
      if (hasSubmissionArtifacts(value)) return true
    }
  }
  return false
}

/** Match only files under run submission/, not doc_manuscript.tex etc. */
export function findSubmissionFile(outputs: Record<string, unknown>, basename: string): string | null {
  function walk(obj: unknown): string | null {
    if (typeof obj === "string" && isFilePath(obj)) {
      if (obj.includes("/submission/") && obj.split("/").pop() === basename) return obj
    } else if (obj && typeof obj === "object" && !Array.isArray(obj)) {
      for (const v of Object.values(obj as Record<string, unknown>)) {
        const found = walk(v)
        if (found) return found
      }
    }
    return null
  }
  return walk(outputs)
}

export function hasCompleteSubmission(outputs: Record<string, unknown>): boolean {
  return Boolean(
    findSubmissionFile(outputs, "manuscript.tex")
    && findSubmissionFile(outputs, "manuscript.docx")
    && findSubmissionFile(outputs, "references.bib"),
  )
}

export function hasPartialSubmission(outputs: Record<string, unknown>): boolean {
  return hasSubmissionArtifacts(outputs) && !hasCompleteSubmission(outputs)
}

export function findFileByName(outputs: Record<string, unknown>, namePart: string): string | null {
  function walk(obj: unknown): string | null {
    if (typeof obj === "string" && isFilePath(obj)) {
      const name = obj.split("/").pop() ?? ""
      if (name.toLowerCase().includes(namePart.toLowerCase())) return obj
    } else if (obj && typeof obj === "object" && !Array.isArray(obj)) {
      for (const v of Object.values(obj as Record<string, unknown>)) {
        const found = walk(v)
        if (found) return found
      }
    }
    return null
  }
  return walk(outputs)
}

export function findAllFilesByExt(outputs: Record<string, unknown>, exts: string[]): string[] {
  const results: string[] = []
  function walk(obj: unknown) {
    if (typeof obj === "string" && isFilePath(obj)) {
      const name = (obj.split("/").pop() ?? "").toLowerCase()
      if (exts.some((ext) => name.endsWith(ext))) results.push(obj)
    } else if (obj && typeof obj === "object" && !Array.isArray(obj)) {
      for (const v of Object.values(obj as Record<string, unknown>)) walk(v)
    }
  }
  walk(outputs)
  return results
}

export function makeUrlTransform(markdownFilePath: string) {
  return (url: string, key: string): string | undefined => {
    if (key === "src" && !/^(https?:\/\/|data:|\/)/i.test(url)) {
      const dir = markdownFilePath.split("/").slice(0, -1).join("/")
      const resolved = dir ? `${dir}/${url}` : url
      return downloadUrl(resolved)
    }
    return defaultUrlTransform(url)
  }
}

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
}

export function extractHeadings(markdown: string): { level: number; text: string; slug: string }[] {
  const headings: { level: number; text: string; slug: string }[] = []
  const re = /^(#{1,3})\s+(.+)$/gm
  let match
  while ((match = re.exec(markdown)) !== null) {
    const text = match[2].trim()
    headings.push({ level: match[1].length, text, slug: slugify(text) })
  }
  return headings
}

export function formatExportError(error: unknown): string {
  const stripExportLabel = (message: string) =>
    message.replace(/^Export failed:\s*/i, "").trim()

  if (error instanceof APIResponseError) {
    if (
      error.detail &&
      typeof error.detail === "object" &&
      "violations" in error.detail &&
      Array.isArray((error.detail as { violations?: unknown[] }).violations)
    ) {
      const violations = (error.detail as { violations: Array<{ code?: string }> }).violations
      const firstCode = violations[0]?.code
      if (firstCode) {
        return `${stripExportLabel(error.message)} (${firstCode}${violations.length > 1 ? ` +${violations.length - 1} more` : ""})`
      }
      return `${stripExportLabel(error.message)} (${violations.length} contract violation${violations.length === 1 ? "" : "s"})`
    }
    return stripExportLabel(error.message)
  }
  if (error instanceof Error) return stripExportLabel(error.message)
  return "Export failed"
}
