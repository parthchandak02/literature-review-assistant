import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/feedback"
import { Download, FileText } from "lucide-react"
import { studyFilesZipUrl } from "@/lib/api"
import { cn } from "@/lib/utils"
import { FilePreview } from "./FilePreview"
import {
  type OutputFile,
  type DocGroup,
  REFERENCE_PAPERS_ZIP_KEY,
  FLAT_DOC_GROUPS,
  collectFiles,
  fileGroupKey,
  fileIcon,
  isFigurePath,
  isPreviewableFile,
  resolveFileUrl,
} from "./artifactFileUtils"
import { RESULTS_DOWNLOAD_BTN_CLS } from "./resultsShared"

export interface ArtifactFileListProps {
  outputs: Record<string, unknown>
  /** File paths already rendered elsewhere that should not appear in this panel. */
  excludePaths?: Set<string>
  /** run_id used for Reference papers only ZIP synthetic row. */
  runId?: string | null
  /** Optional highlight target for deep-linking into Submission Files. */
  submissionFocusTarget?: "reference-papers" | null
  submissionFocusToken?: number
  /** When true, only render figure rows (no document groups). */
  figuresOnly?: boolean
  /** When true, skip the Figures section (document groups only). */
  hideFigures?: boolean
}

function FileRow({ file }: { file: OutputFile }) {
  const { icon: Icon, className: iconClass } = fileIcon(file)
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="flex items-center gap-2 min-w-0">
        <Icon className={`h-4 w-4 shrink-0 ${iconClass}`} />
        <span className="text-sm truncate text-foreground">{file.label}</span>
      </span>
      <Button size="sm" variant="outline" asChild className={`shrink-0 ${RESULTS_DOWNLOAD_BTN_CLS}`}>
        <a href={resolveFileUrl(file.path)} download={file.label} className="gap-1.5">
          <Download className="h-3.5 w-3.5" />
          Download
        </a>
      </Button>
    </div>
  )
}

function SelectableDocRow({
  file,
  selected,
  onSelect,
}: {
  file: OutputFile
  selected: boolean
  onSelect: (file: OutputFile) => void
}) {
  const { icon: Icon, className: iconClass } = fileIcon(file)
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect(file)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          onSelect(file)
        }
      }}
      className={cn(
        "flex items-center justify-between gap-2 rounded-md px-2 py-1.5 -mx-2 cursor-pointer transition-colors",
        selected
          ? "bg-intent-primary-subtle ring-1 ring-intent-primary-border"
          : "hover:bg-surface-2/60",
      )}
    >
      <span className="flex items-center gap-2 min-w-0">
        <Icon className={`h-4 w-4 shrink-0 ${iconClass}`} />
        <span className="text-sm truncate text-foreground">{file.label}</span>
      </span>
      <Button
        size="sm"
        variant="outline"
        asChild
        className={`shrink-0 ${RESULTS_DOWNLOAD_BTN_CLS}`}
        onClick={(e) => e.stopPropagation()}
      >
        <a href={resolveFileUrl(file.path)} download={file.label} className="gap-1.5">
          <Download className="h-3.5 w-3.5" />
          Download
        </a>
      </Button>
    </div>
  )
}

function FigureGridCard({ file }: { file: OutputFile }) {
  const [imgError, setImgError] = useState(false)
  const { icon: Icon, className: iconClass } = fileIcon(file)
  return (
    <figure className="rounded-xl border border-border bg-card overflow-hidden">
      <div className="px-3 py-2 border-b border-border bg-surface-1/60 flex items-center justify-between gap-2">
        <figcaption className="flex items-center gap-2 min-w-0 text-sm font-medium text-foreground">
          <Icon className={`h-4 w-4 shrink-0 ${iconClass}`} />
          <span className="truncate" title={file.label}>
            {file.label}
          </span>
        </figcaption>
        {!imgError ? (
          <Button size="sm" variant="outline" asChild className={`shrink-0 ${RESULTS_DOWNLOAD_BTN_CLS}`}>
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
      {file.isRasterImage && !imgError ? (
        <div className="p-2 aspect-square flex items-center justify-center bg-surface-1/20">
          <img
            src={resolveFileUrl(file.path)}
            alt={file.label}
            className="max-h-full max-w-full rounded-lg object-contain"
            loading="lazy"
            onError={() => setImgError(true)}
          />
        </div>
      ) : null}
    </figure>
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
          <span className="text-sm truncate text-foreground">{file.label}</span>
        </span>
        {!imgError ? (
          <Button size="sm" variant="outline" asChild className={`shrink-0 ${RESULTS_DOWNLOAD_BTN_CLS}`}>
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

function DocGroupsList({
  groupedDocs,
  selectedKey,
  onSelect,
  figsCount,
}: {
  groupedDocs: Record<DocGroup, OutputFile[]>
  selectedKey: string | null
  onSelect: (file: OutputFile) => void
  figsCount: number
}) {
  const hasAnyDocs = FLAT_DOC_GROUPS.some((g) => groupedDocs[g.key].length > 0)
  if (!hasAnyDocs) return null

  return (
    <>
      {FLAT_DOC_GROUPS.map(({ key, label }, idx) => {
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
          <div key={key} className={isLast && figsCount === 0 ? "" : "pb-4 mb-4 border-b border-border/60"}>
            <p className="label-caps pb-2">{label}</p>
            <div className="flex flex-col gap-1">
              {groupFiles.map((f) => (
                <div key={f.key} data-download-key={f.key}>
                  {isPreviewableFile(f) ? (
                    <SelectableDocRow
                      file={f}
                      selected={selectedKey === f.key}
                      onSelect={onSelect}
                    />
                  ) : (
                    <FileRow file={f} />
                  )}
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </>
  )
}

export function ArtifactFileList({
  outputs,
  excludePaths,
  runId = null,
  submissionFocusTarget = null,
  submissionFocusToken = 0,
  figuresOnly = false,
  hideFigures = false,
}: ArtifactFileListProps) {
  const [selectedFile, setSelectedFile] = useState<OutputFile | null>(null)

  const allFiles = collectFiles(outputs)
  const files = excludePaths
    ? allFiles.filter((f) => !excludePaths.has(f.path))
    : allFiles
  const docs = files.filter((f) => !f.isRasterImage && !isFigurePath(f.path))
  const figs = files.filter((f) => isFigurePath(f.path))
  const previewableDocs = docs.filter(isPreviewableFile)
  const hasPreviewPane = previewableDocs.length > 0

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

  const handleSelect = (file: OutputFile) => {
    setSelectedFile((prev) => (prev?.key === file.key ? null : file))
  }

  if (files.length === 0) {
    return <EmptyState icon={FileText} heading="No output files to display." className="py-16" />
  }

  if (figuresOnly) {
    if (figs.length === 0) {
      return <EmptyState icon={FileText} heading="No figures in this run." className="py-10" />
    }
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {figs.map((f) => (
          <FigureGridCard key={f.key} file={f} />
        ))}
      </div>
    )
  }

  const groupedDocs = buildGroupedDocs(docs, runId)

  const listContent = (
    <div className="flex flex-col gap-0">
      <DocGroupsList
        groupedDocs={groupedDocs}
        selectedKey={selectedFile?.key ?? null}
        onSelect={handleSelect}
        figsCount={hideFigures ? 0 : figs.length}
      />

      {!hideFigures && figs.length > 0 && (
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

  if (!hasPreviewPane) {
    return listContent
  }

  return (
    <div className="flex flex-col lg:flex-row gap-4 min-h-[400px]">
      <div className="flex flex-col min-w-0 lg:w-72 xl:w-80 lg:shrink-0 lg:max-h-[70vh] lg:overflow-y-auto">
        {listContent}
      </div>
      <div className="flex-1 min-w-0 lg:border-l lg:border-border lg:pl-4">
        <FilePreview file={selectedFile} />
      </div>
    </div>
  )
}
