import { useEffect, useId, useState } from "react"
import { AlertCircle, CheckCircle2, FileText, Upload, X } from "lucide-react"
import { Spinner } from "@/components/ui/feedback"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { CollapsibleSection } from "@/components/ui/section"
import { cn } from "@/lib/utils"
import type { CsvMode } from "./types"
import { analyzeCsvFile, CSV_EXPECTED_COLS, CSV_REQUIRED_COLS, csvTypeError } from "./csvUtils"
import type { CsvAnalysis } from "./csvUtils"

interface CsvDropZoneProps {
  file: File | null
  onFile: (f: File | null) => void
  mode: CsvMode
  onModeChange: (mode: CsvMode) => void
}

const MODE_OPTIONS: { value: CsvMode; label: string; consequence: string }[] = [
  {
    value: "supplementary",
    label: "Merge with search",
    consequence: "Runs the database search, then adds your CSV rows. Duplicates are removed.",
  },
  {
    value: "masterlist",
    label: "Use as master list",
    consequence: "Skips database search. Only the studies in your CSV are screened.",
  },
]

function readFailure(message: string): CsvAnalysis {
  return {
    rowCount: 0,
    headers: [],
    presentExpected: [],
    missingExpected: CSV_EXPECTED_COLS,
    missingRequired: CSV_REQUIRED_COLS,
    valid: false,
    error: message,
  }
}

export function CsvDropZone({ file, onFile, mode, onModeChange }: CsvDropZoneProps) {
  const [dragging, setDragging] = useState(false)
  const [analysis, setAnalysis] = useState<CsvAnalysis | null>(null)
  const [analysing, setAnalysing] = useState(false)
  const [typeError, setTypeError] = useState<string | null>(null)
  const inputId = useId()
  const errorId = useId()
  const modeLabelId = useId()

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- resetting derived state when file prop clears is intentional
    if (!file) { setAnalysis(null); return }
    let cancelled = false
    setAnalysing(true)
    analyzeCsvFile(file)
      .then((result) => {
        if (!cancelled) setAnalysis(result)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        const detail = error instanceof Error && error.message ? `: ${error.message}` : ""
        setAnalysis(readFailure(`Could not read this CSV${detail}`))
      })
      .finally(() => {
        if (!cancelled) setAnalysing(false)
      })
    return () => {
      cancelled = true
    }
  }, [file])

  function accept(candidate: File | undefined) {
    if (!candidate) return
    const error = csvTypeError(candidate)
    setTypeError(error)
    if (!error) onFile(candidate)
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    accept(e.dataTransfer.files[0])
  }

  return (
    <CollapsibleSection
      icon={FileText}
      title="CSV import (optional)"
      defaultOpen={false}
      className="rounded-lg border-border bg-card shadow-none"
    >
      <div className="p-4 space-y-3">
        <p className="text-xs text-muted leading-relaxed">
          Add a Scopus-style spreadsheet to enrich the automated search, or to replace it with your own list.
        </p>

        <div className="space-y-2">
          <p id={modeLabelId} className="text-xs font-medium text-foreground">How to use the CSV</p>
          <RadioGroup
            value={mode}
            onValueChange={(v) => onModeChange(v as CsvMode)}
            aria-labelledby={modeLabelId}
          >
            {MODE_OPTIONS.map((option) => {
              const id = `${inputId}-${option.value}`
              return (
                <label key={option.value} htmlFor={id} className="flex cursor-pointer items-start gap-2.5">
                  <RadioGroupItem id={id} value={option.value} className="mt-0.5" />
                  <span className="min-w-0 text-xs">
                    <span className="font-medium text-foreground">{option.label}</span>
                    <span className="text-muted">: {option.consequence}</span>
                  </span>
                </label>
              )
            })}
          </RadioGroup>
        </div>

        {!file ? (
          <div>
            <input
              id={inputId}
              type="file"
              accept=".csv,text/csv"
              className="peer sr-only"
              aria-describedby={typeError ? errorId : undefined}
              aria-invalid={typeError ? true : undefined}
              onChange={(e) => {
                accept(e.target.files?.[0])
                e.target.value = ""
              }}
            />
            <label
              htmlFor={inputId}
              onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              className={cn(
                "flex flex-col items-center justify-center gap-2 px-4 py-6 rounded-panel border-2 border-dashed cursor-pointer transition-colors",
                "peer-focus-visible:ring-2 peer-focus-visible:ring-ring peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-background",
                dragging
                  ? "border-intent-success/60 bg-intent-success-subtle"
                  : typeError
                    ? "border-intent-danger-border bg-intent-danger-subtle"
                    : "border-border bg-surface-2/50 hover:bg-surface-2",
              )}
            >
              <Upload className="h-5 w-5 text-muted" aria-hidden />
              <span className="text-xs text-muted text-center leading-relaxed">
                Drop a CSV file here, or <span className="text-intent-success font-medium">browse</span>
              </span>
              <span className="text-xs text-muted">Scopus export format (Title, Authors, Year, DOI, Abstract...).</span>
            </label>
            {typeError && (
              <p id={errorId} role="alert" className="mt-2 flex items-start gap-1.5 text-xs text-intent-danger-text">
                <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" aria-hidden />
                {typeError}
              </p>
            )}
          </div>
        ) : (
          <div className={cn(
            "flex items-center gap-3 px-4 py-3 rounded-panel border",
            analysis?.valid
              ? "border-intent-success-border bg-intent-success-subtle"
              : analysis
                ? "border-intent-warning-border bg-intent-warning-subtle"
                : "border-border bg-surface-2/50",
          )}>
            <FileText className={cn("h-4 w-4 shrink-0", analysis?.valid ? "text-intent-success" : analysis ? "text-intent-warning" : "text-muted")} />
            <div className="flex-1 min-w-0">
              <p className={cn("text-xs font-medium truncate", analysis?.valid ? "text-intent-success" : analysis ? "text-intent-warning" : "text-foreground")}>
                {file.name}
              </p>
              <p className={cn("text-xs mt-0.5", analysis?.valid ? "text-intent-success/70" : "text-muted")}>
                {(file.size / 1024).toFixed(0)} KB
              </p>
            </div>
            <button
              type="button"
              onClick={() => { onFile(null); setAnalysis(null) }}
              className="rounded-sm text-muted hover:text-foreground transition-colors shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Remove file"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        {file && (
          <div className="rounded-panel border border-border bg-card/80 overflow-hidden">
            {analysing && (
              <div className="flex items-center gap-2 px-4 py-3 text-xs text-muted">
                <Spinner size="sm" className="shrink-0" />
                Analysing CSV...
              </div>
            )}

            {analysis && !analysing && (
              <>
                <div
                  role={analysis.valid ? "status" : "alert"}
                  className={cn(
                    "flex items-center gap-2.5 px-4 py-3 border-b border-border/60",
                    analysis.valid ? "bg-intent-success-subtle" : "bg-intent-warning-subtle",
                  )}
                >
                  {analysis.valid ? (
                    <CheckCircle2 className="h-4 w-4 text-intent-success shrink-0" />
                  ) : (
                    <AlertCircle className="h-4 w-4 text-intent-warning shrink-0" />
                  )}
                  <div className="flex-1">
                    {analysis.error ? (
                      <p className="text-xs font-semibold text-intent-danger-text">{analysis.error}</p>
                    ) : analysis.valid ? (
                      <p className="text-xs font-semibold text-intent-success">
                        {analysis.rowCount.toLocaleString()} papers ready to screen
                      </p>
                    ) : analysis.missingRequired.length > 0 ? (
                      <p className="text-xs font-semibold text-intent-warning">
                        Missing required column: {analysis.missingRequired.join(", ")}
                      </p>
                    ) : (
                      <p className="text-xs font-semibold text-intent-warning">
                        {analysis.rowCount === 0 ? "No data rows found" : `${analysis.rowCount.toLocaleString()} rows found`}
                      </p>
                    )}
                  </div>
                </div>

                {!analysis.error && (
                  <div className="px-4 py-3">
                    <p className="text-xs font-semibold text-muted uppercase tracking-wide mb-2">Detected columns</p>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                      {[...CSV_REQUIRED_COLS, ...CSV_EXPECTED_COLS].map((col) => {
                        const present = analysis.headers.includes(col)
                        const required = CSV_REQUIRED_COLS.includes(col)
                        return (
                          <div key={col} className="flex items-center gap-1.5">
                            <div className={cn(
                              "w-1.5 h-1.5 rounded-full shrink-0",
                              present ? "bg-intent-success" : required ? "bg-intent-danger" : "bg-surface-4",
                            )} />
                            <span className={cn(
                              "text-xs truncate",
                              present ? "text-foreground" : required ? "text-intent-danger" : "text-muted",
                            )}>
                              {col}
                              {required && !present && " *"}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                    {analysis.missingExpected.length > 0 && analysis.valid && (
                      <p className="text-xs text-muted mt-2 leading-relaxed">
                        {analysis.missingExpected.length} optional column{analysis.missingExpected.length > 1 ? "s" : ""} not found. Those fields will be blank in the review.
                      </p>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </CollapsibleSection>
  )
}
