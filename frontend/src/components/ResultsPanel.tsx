import { useState, useRef, useCallback } from "react"
import ReactMarkdown, { defaultUrlTransform } from "react-markdown"
import remarkGfm from "remark-gfm"
import rehypeSlug from "rehype-slug"
import rehypeAutolinkHeadings from "rehype-autolink-headings"
import rehypeHighlight from "rehype-highlight"
// highlight.js theme loaded as a side-effect CSS import (Vite resolves npm CSS)
import "highlight.js/styles/github-dark.css"
import { Button } from "@/components/ui/button"
import { Download, FileText, Image, FileCode, ChevronDown, ChevronUp, BookOpen } from "lucide-react"
import { downloadUrl } from "@/lib/api"

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
}

function latexLabel(name: string): string {
  if (name === "manuscript.tex") return "LaTeX manuscript"
  if (name === "references.bib") return "BibTeX references"
  if (/\.tex$/i.test(name)) return `LaTeX: ${name}`
  if (/\.bib$/i.test(name)) return `BibTeX: ${name}`
  return name
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
      files.push({
        key: prefix,
        path: obj,
        label: isLatex ? latexLabel(name) : name,
        isRasterImage: isFigure && isRasterImage,
        isLatex,
        isMarkdown,
        isJson,
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

function FileRow({ label, path, downloadName }: { label: string; path: string; downloadName?: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-sm truncate text-zinc-400">{label}</span>
      <Button size="sm" variant="outline" asChild className="shrink-0 border-zinc-700 text-zinc-400 hover:text-zinc-200">
        <a href={downloadUrl(path)} download={downloadName ?? label} className="gap-1.5">
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

/** Expandable document row with inline viewer for .md and .json files. */
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

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm truncate text-zinc-400">{file.label}</span>
        <div className="flex items-center gap-1.5 shrink-0">
          <Button
            size="sm"
            variant="ghost"
            onClick={handleToggle}
            disabled={loading}
            className="h-7 px-2 text-xs text-zinc-500 hover:text-zinc-200 border border-zinc-800 gap-1"
          >
            {loading ? "Loading..." : open ? (
              <><ChevronUp className="h-3 w-3" />Hide</>
            ) : (
              <><ChevronDown className="h-3 w-3" />View</>
            )}
          </Button>
          <Button size="sm" variant="outline" asChild className="h-7 px-2 border-zinc-700 text-zinc-400 hover:text-zinc-200">
            <a href={downloadUrl(file.path)} download={file.label} className="gap-1.5 text-xs">
              <Download className="h-3 w-3" />
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
          <div
            ref={viewerRef}
            className="overflow-auto max-h-[80vh] p-6"
          >
            {file.isMarkdown ? (
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
            ) : (
              <pre className="text-xs text-zinc-400 whitespace-pre-wrap font-mono">
                {file.isJson ? (() => { try { return JSON.stringify(JSON.parse(content), null, 2) } catch { return content } })() : content}
              </pre>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function FigureRow({ file }: { file: OutputFile }) {
  const [imgError, setImgError] = useState(false)
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm truncate text-zinc-400">{file.label}</span>
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
  // Documents: non-figure, non-latex files. Includes .md and .json which get inline viewer.
  const docs = files.filter(
    (f) => !f.isRasterImage && !f.isLatex && !/\.(png|jpg|jpeg|svg|webp|pdf)$/i.test(f.path),
  )
  const figs = files.filter((f) => /\.(png|jpg|jpeg|svg|webp|pdf)$/i.test(f.path) && !f.isLatex)
  const latex = files.filter((f) => f.isLatex)

  if (files.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <FileText className="h-10 w-10 text-zinc-700 mb-3" />
        <p className="text-zinc-500 text-sm">No output files to display.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {docs.length > 0 && (
        <SectionBox icon={FileText} title="Documents" sub="Manuscript, protocol, appendices">
          {docs.map((f) =>
            f.isMarkdown || f.isJson ? (
              <InlineDocRow key={f.key} file={f} />
            ) : (
              <FileRow key={f.key} label={f.label} path={f.path} />
            ),
          )}
        </SectionBox>
      )}

      {latex.length > 0 && (
        <SectionBox icon={FileCode} title="LaTeX Submission" sub="IEEE-ready .tex + .bib">
          {latex.map((f) => (
            <FileRow key={f.key} label={f.label} path={f.path} downloadName={f.path.split("/").pop()} />
          ))}
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
