import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { Download, FileText, Image, FileCode } from "lucide-react"
import { downloadUrl } from "@/lib/api"

interface ResultsPanelProps {
  outputs: Record<string, unknown>
}

function isFilePath(val: unknown): val is string {
  return typeof val === "string" && (val.startsWith("data/") || val.startsWith("/"))
}

interface OutputFile {
  key: string
  path: string
  label: string
  isImage: boolean
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
      files.push({
        key: prefix,
        path: obj,
        label: isLatex ? latexLabel(name) : name,
        isImage: /\.(png|jpg|jpeg|svg|pdf)$/i.test(name),
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

export function ResultsPanel({ outputs }: ResultsPanelProps) {
  const files = collectFiles(outputs)
  const docs = files.filter((f) => !f.isImage && !f.isLatex)
  const figs = files.filter((f) => f.isImage)
  const latex = files.filter((f) => f.isLatex)

  if (files.length === 0) {
    return (
      <Card>
        <CardContent className="pt-4">
          <p className="text-sm text-muted-foreground">No output files to display.</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {docs.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <FileText className="h-4 w-4" /> Documents
            </CardTitle>
            <CardDescription className="text-xs">Manuscript, protocol, appendices</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {docs.map((f) => (
              <div key={f.key} className="flex items-center justify-between gap-2">
                <span className="text-sm truncate text-muted-foreground">{f.label}</span>
                <Button size="sm" variant="outline" asChild>
                  <a href={downloadUrl(f.path)} download={f.label} className="gap-1.5">
                    <Download className="h-3.5 w-3.5" />
                    Download
                  </a>
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {latex.length > 0 && (
        <>
          {docs.length > 0 && <Separator />}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <FileCode className="h-4 w-4" /> LaTeX Submission
              </CardTitle>
              <CardDescription className="text-xs">
                IEEE-ready .tex manuscript, .bib references, figures
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {latex.map((f) => (
                <div key={f.key} className="flex items-center justify-between gap-2">
                  <span className="text-sm truncate text-muted-foreground">{f.label}</span>
                  <Button size="sm" variant="outline" asChild>
                    <a href={downloadUrl(f.path)} download={f.path.split("/").pop()} className="gap-1.5">
                      <Download className="h-3.5 w-3.5" />
                      Download
                    </a>
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>
        </>
      )}

      {figs.length > 0 && (
        <>
          {(docs.length > 0 || latex.length > 0) && <Separator />}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Image className="h-4 w-4" /> Figures
              </CardTitle>
              <CardDescription className="text-xs">PRISMA flow, forest plot, RoB, geographic</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {figs.map((f) => (
                <div key={f.key} className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-sm truncate text-muted-foreground">{f.label}</span>
                    <Button size="sm" variant="outline" asChild>
                      <a href={downloadUrl(f.path)} download={f.label} className="gap-1.5">
                        <Download className="h-3.5 w-3.5" />
                        Download
                      </a>
                    </Button>
                  </div>
                  <img
                    src={downloadUrl(f.path)}
                    alt={f.label}
                    className="w-full rounded border object-contain max-h-64"
                    loading="lazy"
                  />
                </div>
              ))}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
