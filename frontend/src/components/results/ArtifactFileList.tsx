import { useRef, useCallback, useEffect, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import rehypeSlug from "rehype-slug"
import rehypeAutolinkHeadings from "rehype-autolink-headings"
import rehypeHighlight from "rehype-highlight"
import hljs from "highlight.js/lib/core"
import latex from "highlight.js/lib/languages/latex"
import "highlight.js/styles/github.css"
import { ManuscriptImage } from "@/components/ManuscriptImage"
import { Button } from "@/components/ui/button"
import { Th } from "@/components/ui/table"
import { EmptyState } from "@/components/ui/feedback"
import {
  Download,
  FileText,
  ChevronDown,
  ChevronUp,
  BookOpen,
} from "lucide-react"
import { studyFilesZipUrl } from "@/lib/api"
import { extractHeadings, makeUrlTransform } from "./manuscriptUtils"
import {
  type OutputFile,
  type DocGroup,
  REFERENCE_PAPERS_ZIP_KEY,
  FLAT_DOC_GROUPS,
  collectFiles,
  fileGroupKey,
  fileIcon,
  isFigurePath,
  parseCsv,
  resolveFileUrl,
} from "./artifactFileUtils"

hljs.registerLanguage("latex", latex)

export interface ArtifactFileListProps {
  outputs: Record<string, unknown>
  /** File paths already rendered elsewhere that should not appear in this panel. */
  excludePaths?: Set<string>
  /** run_id used for Reference papers only ZIP synthetic row. */
  runId?: string | null
  /** Optional highlight target for deep-linking into Submission Files. */
  submissionFocusTarget?: "reference-papers" | null
  submissionFocusToken?: number
}

function FileRow({ file }: { file: OutputFile }) {
  const { icon: Icon, className: iconClass } = fileIcon(file)
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="flex items-center gap-2 min-w-0">
        <Icon className={`h-4 w-4 shrink-0 ${iconClass}`} />
        <span className="text-sm truncate text-muted">{file.label}</span>
      </span>
      <Button size="sm" variant="outline" asChild className="shrink-0 border-border text-muted hover:text-foreground">
        <a href={resolveFileUrl(file.path)} download={file.label} className="gap-1.5">
          <Download className="h-3.5 w-3.5" />
          Download
        </a>
      </Button>
    </div>
  )
}

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
    <div className="flex items-center gap-1 px-3 py-2 border-b border-border bg-card overflow-x-auto">
      <BookOpen className="h-3.5 w-3.5 text-muted shrink-0 mr-1" />
      {headings.map((h) => (
        <button
          key={h.slug}
          onClick={() => jumpTo(h.slug)}
          className={[
            "shrink-0 px-2 py-0.5 rounded text-xs transition-colors whitespace-nowrap",
            h.level === 1
              ? "text-foreground font-semibold hover:bg-surface-2"
              : h.level === 2
                ? "text-muted hover:bg-surface-2 hover:text-foreground"
                : "text-muted hover:bg-surface-2 hover:text-muted",
          ].join(" ")}
        >
          {h.text}
        </button>
      ))}
    </div>
  )
}

function CsvViewer({ content }: { content: string }) {
  const rows = parseCsv(content)
  if (rows.length === 0) return <p className="text-xs text-muted p-4">Empty file.</p>
  const [header, ...body] = rows
  return (
    <div className="overflow-auto max-h-[50vh]">
      <table className="text-xs text-foreground border-collapse w-full">
        <thead className="sticky top-0 bg-card">
          <tr>
            {header.map((cell, i) => (
              <Th key={i} className="border border-border whitespace-nowrap">
                {cell}
              </Th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, ri) => (
            <tr key={ri} className={ri % 2 === 0 ? "bg-background" : "bg-card/50"}>
              {row.map((cell, ci) => (
                <td key={ci} className="px-3 py-1.5 border border-border max-w-[20rem] truncate">
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
        <code dangerouslySetInnerHTML={{ __html: highlighted }} />
      </pre>
    </div>
  )
}

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
      const res = await fetch(resolveFileUrl(file.path))
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
    img: ManuscriptImage,
  }

  function renderContent() {
    if (content === null) return null
    if (file.isMarkdown) {
      return (
        <div className="manuscript-prose manuscript-viewer max-w-none">
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
      <pre className="text-xs text-muted whitespace-pre-wrap font-mono p-4">
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
          <span className="text-sm truncate text-muted">{file.label}</span>
        </span>
        <div className="flex items-center gap-1.5 shrink-0">
          <Button
            size="sm"
            variant="ghost"
            onClick={handleToggle}
            disabled={loading}
            className="border border-border gap-1 text-muted hover:text-foreground"
          >
            {loading ? "Loading..." : open ? (
              <><ChevronUp className="h-3.5 w-3.5" />Hide</>
            ) : (
              <><ChevronDown className="h-3.5 w-3.5" />View</>
            )}
          </Button>
          <Button size="sm" variant="outline" asChild className="border-border text-muted hover:text-foreground">
            <a href={resolveFileUrl(file.path)} download={file.label} className="gap-1.5">
              <Download className="h-3.5 w-3.5" />
              Download
            </a>
          </Button>
        </div>
      </div>
      {fetchError && (
        <p className="text-xs text-intent-danger px-1">Could not load file content.</p>
      )}
      {open && content !== null && (
        <div className="rounded-lg border border-border bg-background overflow-hidden flex flex-col">
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
          <span className="text-sm truncate text-muted">{file.label}</span>
        </span>
        {!imgError ? (
          <Button size="sm" variant="outline" asChild className="shrink-0 border-border text-muted hover:text-foreground">
            <a href={resolveFileUrl(file.path)} download={file.label} className="gap-1.5">
              <Download className="h-3.5 w-3.5" />
              Download
            </a>
          </Button>
        ) : (
          <span className="shrink-0 text-xs text-muted border border-border rounded px-2 py-1">
            Not generated
          </span>
        )}
      </div>
      {file.isRasterImage && !imgError && (
        <img
          src={resolveFileUrl(file.path)}
          alt={file.label}
          className="w-full rounded-lg border border-border object-contain max-h-72"
          loading="lazy"
          onError={() => setImgError(true)}
        />
      )}
    </div>
  )
}

function buildGroupedDocs(
  docs: OutputFile[],
  runId: string | null,
): Record<DocGroup, OutputFile[]> {
  const groupedDocs = docs.reduce<Record<DocGroup, OutputFile[]>>(
    (acc, f) => {
      const g = fileGroupKey(f)
      acc[g].push(f)
      return acc
    },
    { manuscript: [], protocol: [], submission: [], data: [] },
  )
  if (runId) {
    const refZipPath = studyFilesZipUrl(runId)
    const hasRow = groupedDocs.submission.some((f) => f.path === refZipPath)
    if (!hasRow) {
      groupedDocs.submission.unshift({
        key: REFERENCE_PAPERS_ZIP_KEY,
        path: refZipPath,
        label: "Reference papers only (ZIP)",
        isRasterImage: false,
        isLatex: false,
        isMarkdown: false,
        isJson: false,
        isCsv: false,
      })
    }
  }
  return groupedDocs
}

export function ArtifactFileList({
  outputs,
  excludePaths,
  runId = null,
  submissionFocusTarget = null,
  submissionFocusToken = 0,
}: ArtifactFileListProps) {
  const allFiles = collectFiles(outputs)
  const files = excludePaths
    ? allFiles.filter((f) => !excludePaths.has(f.path))
    : allFiles
  const docs = files.filter((f) => !f.isRasterImage && !isFigurePath(f.path))
  const figs = files.filter((f) => isFigurePath(f.path))

  useEffect(() => {
    if (submissionFocusTarget !== "reference-papers") return
    const targetKey = REFERENCE_PAPERS_ZIP_KEY
    const highlightClasses = ["ring-1", "ring-intent-primary-border", "bg-intent-primary-subtle", "p-1", "rounded-md"]
    const raf = window.requestAnimationFrame(() => {
      const el = document.querySelector(`[data-download-key="${targetKey}"]`)
      if (el instanceof HTMLElement) {
        el.scrollIntoView({ behavior: "smooth", block: "center" })
        el.classList.add(...highlightClasses)
      }
    })
    const timeout = window.setTimeout(() => {
      const el = document.querySelector(`[data-download-key="${targetKey}"]`)
      if (el instanceof HTMLElement) {
        el.classList.remove(...highlightClasses)
      }
    }, 2500)
    return () => {
      window.clearTimeout(timeout)
      window.cancelAnimationFrame(raf)
    }
  }, [submissionFocusTarget, submissionFocusToken])

  if (files.length === 0) {
    return <EmptyState icon={FileText} heading="No output files to display." className="py-16" />
  }

  const groupedDocs = buildGroupedDocs(docs, runId)
  const hasAnyDocs = FLAT_DOC_GROUPS.some((g) => groupedDocs[g.key].length > 0)

  return (
    <div className="flex flex-col gap-0">
      {hasAnyDocs && FLAT_DOC_GROUPS.map(({ key, label }, idx) => {
        let groupFiles = [...groupedDocs[key]]
        if (key === "submission") {
          groupFiles = groupFiles.filter((f) => !/(^|\/)submission\.zip$/i.test(f.path))
        }
        if (key === "submission") {
          groupFiles.sort((a, b) => {
            if (a.key === REFERENCE_PAPERS_ZIP_KEY) return -1
            if (b.key === REFERENCE_PAPERS_ZIP_KEY) return 1
            return a.label.localeCompare(b.label)
          })
        }
        if (groupFiles.length === 0) return null
        const isLast = idx === FLAT_DOC_GROUPS.filter((g) => groupedDocs[g.key].length > 0).length - 1
        return (
          <div key={key} className={isLast && figs.length === 0 ? "" : "pb-4 mb-4 border-b border-border/60"}>
            <p className="label-caps pb-2">{label}</p>
            <div className="flex flex-col gap-2">
              {groupFiles.map((f) => (
                <div key={f.key} data-download-key={f.key}>
                  {f.isMarkdown || f.isJson || f.isLatex || f.isCsv ? (
                    <InlineDocRow file={f} />
                  ) : (
                    <FileRow file={f} />
                  )}
                </div>
              ))}
            </div>
          </div>
        )
      })}

      {figs.length > 0 && (
        <div>
          <p className="label-caps pb-2">Figures</p>
          <div className="flex flex-col gap-3">
            {figs.map((f) => (
              <FigureRow key={f.key} file={f} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
