import type { ElementType } from "react"
import {
  FileText,
  Image,
  BookMarked,
  FileJson,
  FileCode,
  FileSpreadsheet,
  FileType,
  File,
  Search,
  ClipboardList,
  FileSearch,
  BadgeCheck,
  FileArchive,
  FolderArchive,
  ScrollText,
  Database,
  BarChart3,
  Filter,
  Network,
  ShieldCheck,
} from "lucide-react"
import { downloadUrl } from "@/lib/api"
import { isFilePath } from "./manuscriptUtils"

export interface OutputFile {
  key: string
  path: string
  label: string
  isRasterImage: boolean
  isLatex: boolean
  isMarkdown: boolean
  isJson: boolean
  isCsv: boolean
}

export type DocGroup = "manuscript" | "protocol" | "submission" | "data"

export const REFERENCE_PAPERS_ZIP_KEY = "submission.reference_papers_zip"

export function latexLabel(name: string): string {
  if (name === "manuscript.tex") return "LaTeX manuscript"
  if (name === "references.bib") return "BibTeX references"
  if (/\.tex$/i.test(name)) return `LaTeX: ${name}`
  if (/\.bib$/i.test(name)) return `BibTeX: ${name}`
  return name
}

export function fileIcon(file: OutputFile): { icon: ElementType; className: string } {
  const name = file.path.split("/").pop() ?? ""
  const path = file.path.toLowerCase()
  const lower = name.toLowerCase()

  if (path.includes("/studies-files.zip") || lower.includes("reference papers only")) {
    return { icon: FolderArchive, className: "text-intent-success" }
  }
  if (/\.zip$/i.test(name)) return { icon: FileArchive, className: "text-intent-success" }
  if (/\.bib$/i.test(name)) return { icon: BookMarked, className: "text-intent-primary" }

  if (lower.startsWith("doc_search")) return { icon: Search, className: "text-intent-info" }
  if (lower.startsWith("doc_protocol")) return { icon: ClipboardList, className: "text-intent-warning" }
  if (lower.startsWith("doc_fulltext")) return { icon: FileSearch, className: "text-intent-info" }
  if (lower.startsWith("doc_prospero")) return { icon: BadgeCheck, className: "text-intent-success" }

  if (lower === "data_narrative_synthesis.json") return { icon: ScrollText, className: "text-intent-primary" }
  if (lower === "data_papers_manifest.json") return { icon: Database, className: "text-intent-active" }
  if (lower === "run_summary.json") return { icon: ClipboardList, className: "text-foreground" }

  if (lower.includes("forest")) return { icon: BarChart3, className: "text-intent-info" }
  if (lower.includes("funnel")) return { icon: Filter, className: "text-intent-warning" }
  if (lower.includes("rob") || lower.includes("risk_of_bias")) {
    return { icon: ShieldCheck, className: "text-intent-success" }
  }
  if (lower.includes("network")) return { icon: Network, className: "text-intent-primary" }

  if (/\.docx$/i.test(name)) return { icon: FileType, className: "text-intent-info" }
  if (/\.pdf$/i.test(name)) return { icon: FileText, className: "text-intent-danger" }
  if (/\.json$/i.test(name)) return { icon: FileJson, className: "text-muted" }
  if (/\.csv$/i.test(name)) return { icon: FileSpreadsheet, className: "text-intent-success" }
  if (/\.tex$/i.test(name)) return { icon: FileCode, className: "text-muted" }
  if (/\.bib$/i.test(name)) return { icon: BookMarked, className: "text-muted" }
  if (/\.md$/i.test(name)) return { icon: FileText, className: "text-muted" }
  if (/\.(png|jpg|jpeg|svg|webp)$/i.test(name)) return { icon: Image, className: "text-muted" }
  return { icon: File, className: "text-muted" }
}

export function resolveFileUrl(path: string): string {
  return path.startsWith("/api/") ? path : downloadUrl(path)
}

export function fileGroupKey(file: OutputFile): DocGroup {
  const name = (file.path.split("/").pop() ?? "").toLowerCase()
  if (name.startsWith("doc_prospero")) return "protocol"
  if (
    name === "submission.zip" ||
    name === "references.bib" ||
    name === "cover_letter.md" ||
    name.startsWith("prisma_checklist.")
  ) return "submission"
  if (
    /\.(docx)$/i.test(name) ||
    name === "doc_manuscript.md" ||
    name === "manuscript.tex" ||
    name === "references.bib" ||
    name === "cover_letter.md" ||
    /^manuscript\./i.test(name)
  ) return "manuscript"
  if (
    name.startsWith("doc_protocol") ||
    name.startsWith("doc_search") ||
    name.startsWith("doc_fulltext") ||
    name.startsWith("doc_disagree")
  ) return "protocol"
  return "data"
}

export function collectFiles(outputs: Record<string, unknown>): OutputFile[] {
  const files: OutputFile[] = []

  function walk(obj: unknown, prefix: string) {
    if (typeof obj === "string" && isFilePath(obj)) {
      const name = obj.split("/").pop() ?? obj
      const isLatex = /\.(tex|bib)$/i.test(name)
      const isRasterImage = /\.(png|jpg|jpeg|svg|webp)$/i.test(name)
      const isFigure = isRasterImage || /\.pdf$/i.test(name)
      const isMarkdown = /\.md$/i.test(name)
      const isJson = /\.json$/i.test(name)
      const isCsv = /\.csv$/i.test(name)
      const isSubmissionZip = name.toLowerCase() === "submission.zip"
      files.push({
        key: prefix,
        path: obj,
        label: isSubmissionZip ? "Submission package (ZIP)" : isLatex ? latexLabel(name) : name,
        isRasterImage: isFigure && isRasterImage,
        isLatex,
        isMarkdown,
        isJson,
        isCsv,
      })
    } else if (obj && typeof obj === "object" && !Array.isArray(obj)) {
      for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
        walk(v, prefix ? `${prefix}.${k}` : k)
      }
    }
  }

  walk(outputs, "")
  return files
}

export function parseCsv(text: string): string[][] {
  return text
    .trim()
    .split("\n")
    .map((row) =>
      row
        .split(",")
        .map((cell) => cell.replace(/^"|"$/g, "").trim()),
    )
}

export const FLAT_DOC_GROUPS: { key: DocGroup; label: string }[] = [
  { key: "protocol", label: "Protocol & Search" },
  { key: "submission", label: "Submission Files" },
  { key: "data", label: "Data & Analysis" },
]

export function isFigurePath(path: string): boolean {
  return /\.(png|jpg|jpeg|svg|webp|pdf)$/i.test(path)
}
