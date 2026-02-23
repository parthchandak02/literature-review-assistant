import { useState, useRef, useCallback } from "react"
import ReactMarkdown, { defaultUrlTransform } from "react-markdown"
import remarkGfm from "remark-gfm"
import rehypeSlug from "rehype-slug"
import rehypeAutolinkHeadings from "rehype-autolink-headings"
import rehypeHighlight from "rehype-highlight"
import hljs from "highlight.js/lib/core"
import latex from "highlight.js/lib/languages/latex"
// highlight.js theme loaded as a side-effect CSS import (Vite resolves npm CSS)
import "highlight.js/styles/github-dark.css"
import { Button } from "@/components/ui/button"
import {
  Download,
  FileText,
  Image,
  ChevronDown,
  ChevronUp,
  BookOpen,
  FileJson,
  FileCode,
  BookMarked,
  FileSpreadsheet,
  FileType,
  File,
} from "lucide-react"
import { downloadUrl } from "@/lib/api"

hljs.registerLanguage("latex", latex)

interface ResultsPanelProps {
  outputs: Record<string, unknown>
}

function isFilePath(val: unknown): val is string {
  if (typeof val !== "string") return false
  const t = val.trim()
  return (
    t.startsWith("runs/") ||
    t.startsWith("data/") ||
    t.startsWith("./") ||
    t.startsWith("/")
  )
}

interface OutputFile {
  key: string
  path: string
  label: string
  isRasterImage: boolean
  isLatex: boolean
  isMarkdown: boolean
  isJson: boolean
  isCsv: boolean
}

function latexLabel(name: string): string {
  if (name === "manuscript.tex") return "LaTeX manuscript"
  if (name === "references.bib") return "BibTeX references"
  if (/\.tex$/i.test(name)) return `LaTeX: ${name}`
  if (/\.bib$/i.test(name)) return `BibTeX: ${name}`
  return name
}

function fileIcon(file: OutputFile): { icon: React.ElementType; className: string } {
  const name = file.path.split("/").pop() ?? ""
  if (/\.docx$/i.test(name)) return { icon: FileType, className: "text-blue-400" }
  if (/\.json$/i.test(name)) return { icon: FileJson, className: "text-zinc-500" }
  if (/\.csv$/i.test(name)) return { icon: FileSpreadsheet, className: "text-emerald-500" }
  if (/\.tex$/i.test(name)) return { icon: FileCode, className: "text-zinc-500" }
  if (/\.bib$/i.test(name)) return { icon: BookMarked, className: "text-zinc-500" }
  if (/\.md$/i.test(name)) return { icon: FileText, className: "text-zinc-500" }
  if (/\.(png|jpg|jpeg|svg|webp)$/i.test(name)) return { icon: Image, className: "text-zinc-500" }
  return { icon: File, className: "text-zinc-500" }
}

type DocGroup = "manuscript" | "protocol" | "data"

function fileGroupKey(file: OutputFile): DocGroup {
  const name = (file.path.split("/").pop() ?? "").toLowerCase()
  // Primary deliverables
  if (
    /\.(docx)$/i.test(name) ||
    name === "doc_manuscript.md" ||
    name === "manuscript.tex" ||
    name === "references.bib" ||
    name === "cover_letter.md" ||
    /^manuscript\./i.test(name)
  ) return "manuscript"
  // Protocol and search methodology
  if (
    name.startsWith("doc_protocol") ||
    name.startsWith("doc_search") ||
    name.startsWith("doc_fulltext") ||
    name.startsWith("doc_disagree")
  ) return "protocol"
  // Data and analysis
  return "data"
}

const GROUP_META: Record<DocGroup, { label: string; order: number }> = {
  manuscript: { label: "Manuscript", order: 0 },
  protocol: { label: "Protocol & Search", order: 1 },
  data: { label: "Data & Analysis", order: 2 },
}

function collectFiles(outputs: Record<string, unknown>): OutputFile[] {
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
      files.push({
        key: prefix,
        path: obj,
        label: isLatex ? latexLabel(name) : name,
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

function SectionBox({
  icon: Icon,
  title,
  sub,
  children,
}: {
  icon: React.ElementType
  title: string
  sub?: string
  children: React.ReactNode
}) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-zinc-800">
        <Icon className="h-4 w-4 text-zinc-500" />
        <span className="text-sm font-medium text-zinc-200">{title}</span>
        {sub && <span className="text-xs text-zinc-600 ml-1">{sub}</span>}
      </div>
      <div className="flex flex-col gap-2 p-4">{children}</div>
    </div>
  )
}

function FileRow({ file }: { file: OutputFile }) {
  const { icon: Icon, className: iconClass } = fileIcon(file)
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="flex items-center gap-2 min-w-0">
        <Icon className={`h-4 w-4 shrink-0 ${iconClass}`} />
        <span className="text-sm truncate text-zinc-400">{file.label}</span>
      </span>
      <Button size="sm" variant="outline" asChild className="shrink-0 border-zinc-700 text-zinc-400 hover:text-zinc-200">
        <a href={downloadUrl(file.path)} download={file.label} className="gap-1.5">
          <Download className="h-3.5 w-3.5" />
          Download
        </a>
      </Button>
    </div>
  )
}

/**
 * urlTransform for react-markdown: rewrites relative image src values to
 * backend-servable /api/download URLs, using the markdown file's directory as
 * the base.  Absolute URLs and non-src keys are passed through unchanged.
 */
function makeUrlTransform(markdownFilePath: string) {
  return (url: string, key: string): string | undefined => {
    if (key === "src" && !/^(https?:\/\/|data:|\/)/i.test(url)) {
      const dir = markdownFilePath.split("/").slice(0, -1).join("/")
      const resolved = dir ? `${dir}/${url}` : url
      return downloadUrl(resolved)
    }
    return defaultUrlTransform(url)
  }
}

/** Convert a heading string to a URL-safe slug (mirrors rehype-slug output). */
function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
}

/** Extract top-level headings (h1-h3) from raw markdown text. */
function extractHeadings(markdown: string): { level: number; text: string; slug: string }[] {
  const headings: { level: number; text: string; slug: string }[] = []
  const re = /^(#{1,3})\s+(.+)$/gm
  let match
  while ((match = re.exec(markdown)) !== null) {
    const text = match[2].trim()
    headings.push({ level: match[1].length, text, slug: slugify(text) })
  }
  return headings
}

/** Compact horizontal TOC jump bar rendered above the viewer. */
function TocBar({
  headings,
  viewerRef,
}: {
  headings: { level: number; text: string; slug: string }[]
  viewerRef: React.RefObject<HTMLDivElement | null>
}) {
  if (headings.length === 0) return null

  function jumpTo(slug: string) {
    const container = viewerRef.current
    if (!container) return
    const target = container.querySelector(`#${CSS.escape(slug)}`) as HTMLElement | null
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" })
    }
  }

  return (
    <div className="flex items-center gap-1 px-3 py-2 border-b border-zinc-800 bg-zinc-950 overflow-x-auto">
      <BookOpen className="h-3.5 w-3.5 text-zinc-600 shrink-0 mr-1" />
      {headings.map((h) => (
        <button
          key={h.slug}
          onClick={() => jumpTo(h.slug)}
          className={[
            "shrink-0 px-2 py-0.5 rounded text-xs transition-colors whitespace-nowrap",
            h.level === 1
              ? "text-zinc-200 font-semibold hover:bg-zinc-800"
              : h.level === 2
                ? "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
                : "text-zinc-600 hover:bg-zinc-800 hover:text-zinc-400",
          ].join(" ")}
        >
          {h.text}
        </button>
      ))}
    </div>
  )
}

/** Parse a simple CSV string into rows of cells. */
function parseCsv(text: string): string[][] {
  return text
    .trim()
    .split("\n")
    .map((row) =>
      row
        .split(",")
        .map((cell) => cell.replace(/^"|"$/g, "").trim()),
    )
}

/** Inline CSV table viewer. */
function CsvViewer({ content }: { content: string }) {
  const rows = parseCsv(content)
  if (rows.length === 0) return <p className="text-xs text-zinc-600 p-4">Empty file.</p>
  const [header, ...body] = rows
  return (
    <div className="overflow-auto max-h-[50vh]">
      <table className="text-xs text-zinc-300 border-collapse w-full">
        <thead className="sticky top-0 bg-zinc-900">
          <tr>
            {header.map((cell, i) => (
              <th
                key={i}
                className="text-left px-3 py-2 border border-zinc-700 font-semibold text-zinc-200 whitespace-nowrap"
              >
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, ri) => (
            <tr key={ri} className={ri % 2 === 0 ? "bg-zinc-950" : "bg-zinc-900/50"}>
              {row.map((cell, ci) => (
                <td key={ci} className="px-3 py-1.5 border border-zinc-800 max-w-[20rem] truncate">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Inline syntax-highlighted viewer for .tex and .bib files. */
function LatexViewer({ content, isLatex }: { content: string; isLatex: boolean }) {
  let highlighted = content
  try {
    if (isLatex) {
      highlighted = hljs.highlight(content, { language: "latex" }).value
    }
  } catch {
    // fallback to plain text if language not recognized
  }
  return (
    <div className="overflow-auto max-h-[70vh]">
      <pre className="hljs text-xs p-4 font-mono leading-relaxed whitespace-pre-wrap">
        {/* eslint-disable-next-line react/no-danger */}
        <code dangerouslySetInnerHTML={{ __html: highlighted }} />
      </pre>
    </div>
  )
}

/** Expandable document row with inline viewer for .md, .json, .tex, .bib, and .csv files. */
function InlineDocRow({ file }: { file: OutputFile }) {
  const [open, setOpen] = useState(false)
  const [content, setContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [fetchError, setFetchError] = useState(false)
  const viewerRef = useRef<HTMLDivElement>(null)

  const handleToggle = useCallback(async () => {
    if (open) { setOpen(false); return }
    if (content !== null) { setOpen(true); return }
    setLoading(true)
    setFetchError(false)
    try {
      const res = await fetch(downloadUrl(file.path))
      if (!res.ok) throw new Error("fetch failed")
      setContent(await res.text())
      setOpen(true)
    } catch {
      setFetchError(true)
    } finally {
      setLoading(false)
    }
  }, [open, content, file.path])

  const headings = file.isMarkdown && content ? extractHeadings(content) : []

  const markdownComponents = {
    img({ src, alt }: { src?: string; alt?: string }) {
      return (
        <img
          src={src}
          alt={alt ?? ""}
          className="max-w-full rounded border border-zinc-800 my-4 mx-auto block"
          loading="lazy"
        />
      )
    },
  }

  function renderContent() {
    if (content === null) return null
    if (file.isMarkdown) {
      return (
        <div className="prose prose-invert prose-zinc max-w-none manuscript-viewer">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeSlug, [rehypeAutolinkHeadings, { behavior: "wrap" }], rehypeHighlight]}
            urlTransform={makeUrlTransform(file.path)}
            components={markdownComponents}
          >
            {content}
          </ReactMarkdown>
        </div>
      )
    }
    if (file.isCsv) {
      return <CsvViewer content={content} />
    }
    if (file.isLatex) {
      return <LatexViewer content={content} isLatex={/\.tex$/i.test(file.path)} />
    }
    return (
      <pre className="text-xs text-zinc-400 whitespace-pre-wrap font-mono p-4">
        {file.isJson
          ? (() => { try { return JSON.stringify(JSON.parse(content), null, 2) } catch { return content } })()
          : content}
      </pre>
    )
  }

  const { icon: Icon, className: iconClass } = fileIcon(file)

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 min-w-0">
          <Icon className={`h-4 w-4 shrink-0 ${iconClass}`} />
          <span className="text-sm truncate text-zinc-400">{file.label}</span>
        </span>
        <div className="flex items-center gap-1.5 shrink-0">
          <Button
            size="sm"
            variant="ghost"
            onClick={handleToggle}
            disabled={loading}
            className="border border-zinc-800 gap-1 text-zinc-500 hover:text-zinc-200"
          >
            {loading ? "Loading..." : open ? (
              <><ChevronUp className="h-3.5 w-3.5" />Hide</>
            ) : (
              <><ChevronDown className="h-3.5 w-3.5" />View</>
            )}
          </Button>
          <Button size="sm" variant="outline" asChild className="border-zinc-700 text-zinc-400 hover:text-zinc-200">
            <a href={downloadUrl(file.path)} download={file.label} className="gap-1.5">
              <Download className="h-3.5 w-3.5" />
              Download
            </a>
          </Button>
        </div>
      </div>
      {fetchError && (
        <p className="text-xs text-red-400 px-1">Could not load file content.</p>
      )}
      {open && content !== null && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-950 overflow-hidden flex flex-col">
          {file.isMarkdown && <TocBar headings={headings} viewerRef={viewerRef} />}
          <div ref={viewerRef} className={file.isMarkdown ? "overflow-auto max-h-[80vh] p-6" : ""}>
            {renderContent()}
          </div>
        </div>
      )}
    </div>
  )
}

function FigureRow({ file }: { file: OutputFile }) {
  const [imgError, setImgError] = useState(false)
  const { icon: Icon, className: iconClass } = fileIcon(file)
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 min-w-0">
          <Icon className={`h-4 w-4 shrink-0 ${iconClass}`} />
          <span className="text-sm truncate text-zinc-400">{file.label}</span>
        </span>
        {!imgError ? (
          <Button size="sm" variant="outline" asChild className="shrink-0 border-zinc-700 text-zinc-400 hover:text-zinc-200">
            <a href={downloadUrl(file.path)} download={file.label} className="gap-1.5">
              <Download className="h-3.5 w-3.5" />
              Download
            </a>
          </Button>
        ) : (
          <span className="shrink-0 text-xs text-zinc-600 border border-zinc-800 rounded px-2 py-1">
            Not generated
          </span>
        )}
      </div>
      {file.isRasterImage && !imgError && (
        <img
          src={downloadUrl(file.path)}
          alt={file.label}
          className="w-full rounded-lg border border-zinc-800 object-contain max-h-72"
          loading="lazy"
          onError={() => setImgError(true)}
        />
      )}
    </div>
  )
}

export function ResultsPanel({ outputs }: ResultsPanelProps) {
  const files = collectFiles(outputs)
  const docs = files.filter(
    (f) => !f.isRasterImage && !/\.(png|jpg|jpeg|svg|webp|pdf)$/i.test(f.path),
  )
  const figs = files.filter((f) => /\.(png|jpg|jpeg|svg|webp|pdf)$/i.test(f.path))

  if (files.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <FileText className="h-10 w-10 text-zinc-700 mb-3" />
        <p className="text-zinc-500 text-sm">No output files to display.</p>
      </div>
    )
  }

  // Group docs into logical buckets and sort by group order
  const groupedDocs = docs.reduce<Record<DocGroup, OutputFile[]>>(
    (acc, f) => {
      const g = fileGroupKey(f)
      acc[g].push(f)
      return acc
    },
    { manuscript: [], protocol: [], data: [] },
  )
  const orderedGroups = (Object.keys(GROUP_META) as DocGroup[]).sort(
    (a, b) => GROUP_META[a].order - GROUP_META[b].order,
  )

  return (
    <div className="flex flex-col gap-4">
      {docs.length > 0 && (
        <SectionBox
          icon={FileText}
          title="Documents"
          sub="Manuscript, protocol, data"
        >
          {orderedGroups.map((group) => {
            const groupFiles = groupedDocs[group]
            if (groupFiles.length === 0) return null
            return (
              <div key={group} className="flex flex-col gap-2">
                <p className="text-xs text-zinc-600 uppercase tracking-wider pt-1 pb-0.5 border-b border-zinc-800/60">
                  {GROUP_META[group].label}
                </p>
                {groupFiles.map((f) =>
                  f.isMarkdown || f.isJson || f.isLatex || f.isCsv ? (
                    <InlineDocRow key={f.key} file={f} />
                  ) : (
                    <FileRow key={f.key} file={f} />
                  ),
                )}
              </div>
            )
          })}
        </SectionBox>
      )}

      {figs.length > 0 && (
        <SectionBox icon={Image} title="Figures" sub="PRISMA flow, forest plot, RoB, geographic">
          {figs.map((f) => (
            <FigureRow key={f.key} file={f} />
          ))}
        </SectionBox>
      )}
    </div>
  )
}
