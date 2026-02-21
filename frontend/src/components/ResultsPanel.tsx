import { Button } from "@/components/ui/button"
import { Download, FileText, Image, FileCode } from "lucide-react"
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
      // Only PNG/JPG/JPEG/SVG/WebP are safe for inline <img>; PDFs are download-only
      const isRasterImage = /\.(png|jpg|jpeg|svg|webp)$/i.test(name)
      const isFigure = isRasterImage || /\.pdf$/i.test(name)
      files.push({
        key: prefix,
        path: obj,
        label: isLatex ? latexLabel(name) : name,
        isRasterImage: isFigure && isRasterImage,
        isLatex,
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

export function ResultsPanel({ outputs }: ResultsPanelProps) {
  const files = collectFiles(outputs)
  const docs = files.filter((f) => !f.isRasterImage && !f.isLatex && !/\.(png|jpg|jpeg|svg|webp|pdf)$/i.test(f.path))
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
          {docs.map((f) => (
            <FileRow key={f.key} label={f.label} path={f.path} />
          ))}
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
            <div key={f.key} className="flex flex-col gap-2">
              <FileRow label={f.label} path={f.path} />
              {f.isRasterImage && (
                <img
                  src={downloadUrl(f.path)}
                  alt={f.label}
                  className="w-full rounded-lg border border-zinc-800 object-contain max-h-72"
                  loading="lazy"
                />
              )}
            </div>
          ))}
        </SectionBox>
      )}
    </div>
  )
}
