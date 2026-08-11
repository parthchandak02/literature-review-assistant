import { useRef } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import rehypeSlug from "rehype-slug"
import rehypeAutolinkHeadings from "rehype-autolink-headings"
import rehypeHighlight from "rehype-highlight"
import hljs from "highlight.js/lib/core"
import latex from "highlight.js/lib/languages/latex"
import { BookOpen, FileText } from "lucide-react"
import { ManuscriptImage } from "@/components/ManuscriptImage"
import { Th } from "@/components/ui/table"
import { EmptyState, Spinner } from "@/components/ui/feedback"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { useFilePreview } from "@/hooks/useFilePreview"
import { extractHeadings, makeUrlTransform } from "./manuscriptUtils"
import {
  type OutputFile,
  fileIcon,
  parseCsv,
} from "./artifactFileUtils"

hljs.registerLanguage("latex", latex)

export interface FilePreviewProps {
  file: OutputFile | null
  className?: string
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
          className={cn(
            "shrink-0 px-2 py-0.5 rounded text-xs transition-colors whitespace-nowrap",
            h.level === 1
              ? "text-foreground font-semibold hover:bg-surface-2"
              : h.level === 2
                ? "text-muted hover:bg-surface-2 hover:text-foreground"
                : "text-muted hover:bg-surface-2 hover:text-muted",
          )}
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

function PreviewContent({ file, content }: { file: OutputFile; content: string }) {
  const viewerRef = useRef<HTMLDivElement>(null)
  const headings = file.isMarkdown ? extractHeadings(content) : []

  if (file.isMarkdown) {
    return (
      <div className="rounded-lg border border-border bg-background overflow-hidden flex flex-col h-full">
        <TocBar headings={headings} viewerRef={viewerRef} />
        <div ref={viewerRef} className="overflow-auto max-h-[70vh] p-6 flex-1">
          <div className="manuscript-prose manuscript-viewer max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeSlug, [rehypeAutolinkHeadings, { behavior: "wrap" }], rehypeHighlight]}
              urlTransform={makeUrlTransform(file.path)}
              components={{ img: ManuscriptImage }}
            >
              {content}
            </ReactMarkdown>
          </div>
        </div>
      </div>
    )
  }

  if (file.isCsv) {
    return (
      <div className="rounded-lg border border-border bg-background overflow-hidden">
        <CsvViewer content={content} />
      </div>
    )
  }

  if (file.isLatex) {
    return (
      <div className="rounded-lg border border-border bg-background overflow-hidden">
        <LatexViewer content={content} isLatex={/\.tex$/i.test(file.path)} />
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-border bg-background overflow-hidden">
      <pre className="text-xs text-muted whitespace-pre-wrap font-mono p-4 overflow-auto max-h-[70vh]">
        {file.isJson
          ? (() => { try { return JSON.stringify(JSON.parse(content), null, 2) } catch { return content } })()
          : content}
      </pre>
    </div>
  )
}

export function FilePreview({ file, className }: FilePreviewProps) {
  const { content, loading, error, retry } = useFilePreview(file)

  if (!file) {
    return (
      <EmptyState
        icon={FileText}
        heading="Select a file to preview"
        className={cn("py-16 border border-dashed border-border rounded-lg", className)}
      />
    )
  }

  const { icon: Icon, className: iconClass } = fileIcon(file)

  return (
    <div className={cn("flex flex-col gap-2 min-h-[200px]", className)}>
      <div className="flex items-center gap-2 px-1">
        <Icon className={cn("h-4 w-4 shrink-0", iconClass)} />
        <span className="text-sm font-medium text-foreground truncate">{file.label}</span>
      </div>

      {loading && (
        <div className="flex items-center justify-center gap-2 py-16 border border-border rounded-lg bg-background">
          <Spinner size="sm" />
          <span className="text-sm text-muted">Loading preview...</span>
        </div>
      )}

      {error && !loading && (
        <div className="flex flex-col items-center gap-3 py-16 border border-border rounded-lg bg-background">
          <p className="text-sm text-intent-danger">Could not load file content.</p>
          <Button size="sm" variant="outline" onClick={retry}>
            Retry
          </Button>
        </div>
      )}

      {!loading && !error && content !== null && (
        <PreviewContent file={file} content={content} />
      )}
    </div>
  )
}
