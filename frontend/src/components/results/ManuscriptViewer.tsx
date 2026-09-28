import { useCallback, useLayoutEffect, useMemo, useRef, useState, type ComponentProps } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import rehypeSlug from "rehype-slug"
import rehypeAutolinkHeadings from "rehype-autolink-headings"
import rehypeHighlight from "rehype-highlight"
import { AlertTriangle, BookOpen, ChevronDown, Minus, Plus } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { FetchError, Spinner } from "@/components/ui/feedback"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ManuscriptImage } from "@/components/ManuscriptImage"
import { ManuscriptActions } from "@/components/results/ManuscriptActions"
import { useFileTextPreview } from "@/hooks/useFilePreview"
import { extractHeadings, makeUrlTransform } from "./manuscriptUtils"
import { detectTemplateText, type TemplateTextMatch } from "./draftQuality"
import { useScrollSpy } from "./tocScrollSpy"

const ZOOM_MIN = 70
const ZOOM_MAX = 160
const ZOOM_STEP = 15

interface TocItem {
  slug: string
  text: string
  level: number
}

interface ManuscriptViewerProps {
  filePath: string
  docxPath: string | null
  canExport: boolean
  exportRunId: string | null | undefined
  allOutputs: Record<string, unknown>
}

function ManuscriptTable(props: ComponentProps<"table">) {
  return (
    <div className="manuscript-table-wrap overflow-x-auto">
      <table {...props} />
    </div>
  )
}

const MARKDOWN_COMPONENTS = { img: ManuscriptImage, table: ManuscriptTable }

function scrollParent(el: HTMLElement): HTMLElement | null {
  let node = el.parentElement
  while (node) {
    const { overflowY } = getComputedStyle(node)
    if (overflowY === "auto" || overflowY === "scroll") return node
    node = node.parentElement
  }
  return null
}

function tocIndent(level: number) {
  return level === 1 ? "pl-2 font-medium" : level === 2 ? "pl-4" : "pl-6"
}

function TocRail({
  items,
  activeSlug,
  onJump,
}: {
  items: TocItem[]
  activeSlug: string | null
  onJump: (slug: string) => void
}) {
  return (
    <nav
      aria-label="Manuscript outline"
      className="manuscript-toc hidden lg:block sticky top-14 self-start max-h-[calc(100vh-10rem)] overflow-y-auto"
    >
      <p className="label-caps pb-2 pl-2">Outline</p>
      <ul className="flex flex-col gap-px border-l border-border">
        {items.map((h) => {
          const active = h.slug === activeSlug
          return (
            <li key={h.slug}>
              <a
                href={`#${h.slug}`}
                aria-current={active ? "location" : undefined}
                onClick={(e) => {
                  e.preventDefault()
                  onJump(h.slug)
                }}
                className={cn(
                  "-ml-px block border-l-2 py-1 pr-2 text-xs leading-snug transition-colors",
                  tocIndent(h.level),
                  active
                    ? "border-intent-primary text-foreground"
                    : "border-transparent text-muted hover:text-foreground",
                )}
              >
                {h.text}
              </a>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

function DraftQualityChip({ matches }: { matches: TemplateTextMatch[] }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-pill border border-intent-warning-border bg-intent-warning-subtle px-2 py-0.5 text-2xs font-medium text-intent-warning-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <AlertTriangle className="h-3 w-3" aria-hidden />
          Draft quality
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-80 p-3">
        <p className="text-xs font-medium text-foreground">Template text found in the manuscript</p>
        <p className="mt-1 text-2xs text-muted">
          Edit these passages before submitting, or rerun the writing phase.
        </p>
        <ul className="mt-2 flex flex-col gap-2">
          {matches.map((m) => (
            <li key={m.id} className="text-xs">
              <span className="font-medium text-intent-warning-text">{m.label}</span>
              <span className="mt-0.5 block text-muted">“{m.excerpt}”</span>
            </li>
          ))}
        </ul>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function ManuscriptViewer({
  filePath,
  docxPath,
  canExport,
  exportRunId,
  allOutputs,
}: ManuscriptViewerProps) {
  const { content, loading, error, retry } = useFileTextPreview(filePath)
  const [zoom, setZoom] = useState(100)
  const [article, setArticle] = useState<HTMLElement | null>(null)
  const [tocItems, setTocItems] = useState<TocItem[]>([])
  const toolbarRef = useRef<HTMLDivElement>(null)

  const hasHeadings = useMemo(() => (content ? extractHeadings(content).length > 0 : false), [content])
  const templateMatches = useMemo(() => detectTemplateText(content), [content])

  useLayoutEffect(() => {
    if (!article) return
    const items = Array.from(article.querySelectorAll<HTMLElement>("h1[id], h2[id], h3[id]")).map((el) => ({
      slug: el.id,
      text: el.textContent?.trim() ?? "",
      level: Number(el.tagName.slice(1)),
    }))
    // eslint-disable-next-line react-hooks/set-state-in-effect -- headings come from the rendered DOM (rehype-slug ids)
    setTocItems(items)
  }, [article, content])

  const getActivationLine = useCallback(() => {
    const toolbar = toolbarRef.current
    if (!toolbar) return 0
    const scroller = scrollParent(toolbar)
    const top = scroller ? scroller.getBoundingClientRect().top : 0
    return top + toolbar.offsetHeight + 24
  }, [])
  const slugs = useMemo(() => tocItems.map((t) => t.slug), [tocItems])
  const activeSlug = useScrollSpy(slugs, article, getActivationLine)

  const jumpTo = useCallback(
    (slug: string) => {
      const target = article?.querySelector<HTMLElement>(`#${CSS.escape(slug)}`)
      target?.scrollIntoView({ behavior: "smooth", block: "start" })
    },
    [article],
  )

  if (loading) {
    return (
      <div className="overflow-hidden">
        <div className="px-6 py-4 border-b border-border flex items-center gap-2">
          <Spinner size="sm" />
          <span className="text-sm text-muted">Loading manuscript…</span>
        </div>
        <div className="p-6 space-y-4">
          <Skeleton className="h-7 w-2/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-6 w-1/2 mt-6" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
        </div>
      </div>
    )
  }

  if (error) {
    return <FetchError message={`Could not load manuscript: ${error}`} onRetry={retry} />
  }

  if (!content) return null

  const showToc = hasHeadings && tocItems.length > 0

  return (
    <div>
      <div ref={toolbarRef} className="manuscript-toolbar sticky top-0 z-20">
        <ViewToolbar
          dense
          height="auto"
          className="flex-wrap"
          title={
            <div className="flex items-center gap-2">
              {showToc && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button type="button" size="xs" variant="ghost" className="lg:hidden">
                      <BookOpen />
                      Outline
                      <ChevronDown />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="max-h-80 w-72 overflow-y-auto">
                    {tocItems.map((h) => (
                      <DropdownMenuItem
                        key={h.slug}
                        onSelect={() => jumpTo(h.slug)}
                        aria-current={h.slug === activeSlug ? "location" : undefined}
                        className={cn("text-xs", tocIndent(h.level), h.slug === activeSlug && "text-foreground")}
                      >
                        <span className="truncate">{h.text}</span>
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
              {templateMatches.length > 0 && <DraftQualityChip matches={templateMatches} />}
            </div>
          }
          actions={
            <div className="flex flex-wrap items-center justify-end gap-2">
              <ManuscriptActions
                docxPath={docxPath}
                canExport={canExport}
                exportRunId={exportRunId}
                allOutputs={allOutputs}
              />
              <div className="flex items-center gap-0.5 border-l border-border/70 pl-2" role="group" aria-label="Zoom">
                <Button
                  type="button"
                  size="icon-sm"
                  variant="ghost"
                  onClick={() => setZoom((z) => Math.max(ZOOM_MIN, z - ZOOM_STEP))}
                  disabled={zoom <= ZOOM_MIN}
                  aria-label="Zoom out"
                  title="Zoom out"
                >
                  <Minus />
                </Button>
                <button
                  type="button"
                  onClick={() => setZoom(100)}
                  aria-label={`Zoom ${zoom}%, reset to 100%`}
                  title="Reset zoom"
                  className="w-11 rounded-control py-1 text-center text-xs font-mono tabular-nums text-muted hover:bg-surface-2 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {zoom}%
                </button>
                <Button
                  type="button"
                  size="icon-sm"
                  variant="ghost"
                  onClick={() => setZoom((z) => Math.min(ZOOM_MAX, z + ZOOM_STEP))}
                  disabled={zoom >= ZOOM_MAX}
                  aria-label="Zoom in"
                  title="Zoom in"
                >
                  <Plus />
                </Button>
              </div>
            </div>
          }
        />
      </div>

      <div
        className={cn(
          "px-5 py-8 md:px-10",
          showToc && "lg:grid lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-10",
        )}
      >
        {showToc && <TocRail items={tocItems} activeSlug={activeSlug} onJump={jumpTo} />}
        <article
          ref={setArticle}
          className="manuscript-prose manuscript-viewer mx-auto max-w-[68ch]"
          style={{ fontSize: `${zoom}%` }}
        >
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[
              rehypeSlug,
              [rehypeAutolinkHeadings, { behavior: "wrap" }],
              rehypeHighlight,
            ]}
            urlTransform={makeUrlTransform(filePath)}
            components={MARKDOWN_COMPONENTS}
          >
            {content}
          </ReactMarkdown>
        </article>
      </div>
    </div>
  )
}
