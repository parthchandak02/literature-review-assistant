import { useEffect, useRef, useState } from "react"
import { AlertCircle, CheckCircle2, FileText, HelpCircle, Upload, X } from "lucide-react"
import { Spinner } from "@/components/ui/feedback"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import type { CsvMode } from "./types"
import { analyzeCsvFile, CSV_EXPECTED_COLS, CSV_REQUIRED_COLS } from "./csvUtils"
import type { CsvAnalysis } from "./csvUtils"

interface CsvDropZoneProps {
  file: File | null
  onFile: (f: File | null) => void
  mode: CsvMode
  onModeChange: (mode: CsvMode) => void
}

export function CsvDropZone({ file, onFile, mode, onModeChange }: CsvDropZoneProps) {
  const [dragging, setDragging] = useState(false)
  const [analysis, setAnalysis] = useState<CsvAnalysis | null>(null)
  const [analysing, setAnalysing] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- resetting derived state when file prop clears is intentional
    if (!file) { setAnalysis(null); return }
    setAnalysing(true)
    analyzeCsvFile(file).then((result) => {
      setAnalysis(result)
      setAnalysing(false)
    }).catch(() => setAnalysing(false))
  }, [file])

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped && dropped.name.endsWith(".csv")) onFile(dropped)
  }

  function handleAccept(f: File | undefined) {
    if (f) onFile(f)
  }

  const mergeTooltip = "Run connector search first, then merge your CSV rows. Duplicates are removed."
  const masterTooltip = "Skip connector search and use only the studies in your CSV."

  return (
    <TooltipProvider delayDuration={250}>
      <div>
        <div className="flex items-center gap-1.5 mb-2">
          <label className="text-xs font-semibold text-muted uppercase tracking-wide cursor-default">
            CSV Import <span className="text-muted">(optional)</span>
          </label>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                className="text-muted hover:text-intent-info transition-colors rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-intent-primary-border"
                aria-label="About optional CSV import"
              >
                <HelpCircle className="h-3.5 w-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent
              side="top"
              align="start"
              sideOffset={6}
              className="max-w-[260px] text-xs leading-relaxed px-3 py-2.5 bg-card border border-border text-foreground shadow-xl"
            >
              <p className="font-semibold text-foreground mb-1">Optional CSV</p>
              <p>Add a Scopus-style spreadsheet to either enrich automated search or replace it with your fixed list.</p>
            </TooltipContent>
          </Tooltip>
        </div>

        <div
          className="inline-flex rounded-lg border border-border bg-surface-2/70 p-0.5 gap-0.5 mb-2"
          role="radiogroup"
          aria-label="How to use the CSV"
        >
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                role="radio"
                aria-checked={mode === "supplementary"}
                onClick={() => onModeChange("supplementary")}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors min-w-0 ${
                  mode === "supplementary"
                    ? "bg-intent-primary-subtle text-foreground shadow-sm ring-1 ring-intent-primary-border"
                    : "text-muted hover:text-foreground"
                }`}
              >
                Merge with search
              </button>
            </TooltipTrigger>
            <TooltipContent
              side="bottom"
              sideOffset={6}
              className="max-w-[260px] text-xs leading-relaxed px-3 py-2.5 bg-card border border-border text-foreground shadow-xl"
            >
              <p>{mergeTooltip}</p>
            </TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                role="radio"
                aria-checked={mode === "masterlist"}
                onClick={() => onModeChange("masterlist")}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors min-w-0 ${
                  mode === "masterlist"
                    ? "bg-intent-primary-subtle text-foreground shadow-sm ring-1 ring-intent-primary-border"
                    : "text-muted hover:text-foreground"
                }`}
              >
                Use as master list
              </button>
            </TooltipTrigger>
            <TooltipContent
              side="bottom"
              sideOffset={6}
              className="max-w-[260px] text-xs leading-relaxed px-3 py-2.5 bg-card border border-border text-foreground shadow-xl"
            >
              <p>{masterTooltip}</p>
            </TooltipContent>
          </Tooltip>
        </div>

        {/* Drop zone / file picker */}
      {!file ? (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          className={`flex flex-col items-center justify-center gap-2 px-4 py-6 rounded-xl border-2 border-dashed cursor-pointer transition-colors ${
            dragging
              ? "border-intent-success/60 bg-intent-success-subtle"
              : "border-border bg-surface-2/50 hover:border-border hover:bg-surface-2"
          }`}
        >
          <Upload className="h-5 w-5 text-muted" />
          <p className="text-xs text-muted text-center leading-relaxed">
            Drop a CSV file here, or{" "}
            <span className="text-intent-success font-medium">click to browse</span>
          </p>
          <p className="text-xs text-muted">
            {mode === "masterlist"
              ? "Use your curated study list as the primary input."
              : "Scopus export format (Title, Authors, Year, DOI, Abstract...)."}
          </p>
        </div>
      ) : (
        /* File info row */
        <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border ${
          analysis?.valid
            ? "border-intent-success-border bg-intent-success-subtle"
            : analysis && !analysis.valid
            ? "border-intent-warning-border bg-intent-warning-subtle"
            : "border-border bg-surface-2/50"
        }`}>
          <FileText className={`h-4 w-4 shrink-0 ${analysis?.valid ? "text-intent-success" : analysis ? "text-intent-warning" : "text-muted"}`} />
          <div className="flex-1 min-w-0">
            <p className={`text-xs font-medium truncate ${analysis?.valid ? "text-intent-success" : analysis ? "text-intent-warning" : "text-foreground"}`}>
              {file.name}
            </p>
            <p className={`text-xs mt-0.5 ${analysis?.valid ? "text-intent-success/70" : "text-muted"}`}>
              {(file.size / 1024).toFixed(0)} KB
            </p>
          </div>
          <button
            type="button"
            onClick={() => { onFile(null); setAnalysis(null) }}
            className="text-muted hover:text-foreground transition-colors shrink-0"
            aria-label="Remove file"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Validation panel */}
      {file && (
        <div className="mt-2 rounded-xl border border-border bg-card/80 overflow-hidden">
          {analysing && (
            <div className="flex items-center gap-2 px-4 py-3 text-xs text-muted">
              <Spinner size="sm" className="shrink-0" />
              Analysing CSV...
            </div>
          )}

          {analysis && !analysing && (
            <>
              {/* Status row */}
              <div className={`flex items-center gap-2.5 px-4 py-3 border-b border-border/60 ${analysis.valid ? "bg-intent-success-subtle" : "bg-intent-warning-subtle"}`}>
                {analysis.valid ? (
                  <CheckCircle2 className="h-4 w-4 text-intent-success shrink-0" />
                ) : (
                  <AlertCircle className="h-4 w-4 text-intent-warning shrink-0" />
                )}
                <div className="flex-1">
                  {analysis.error ? (
                    <p className="text-xs font-semibold text-intent-danger">{analysis.error}</p>
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
                  {analysis.valid && (
                    <p className="text-xs text-intent-success/70 mt-0.5">
                      {mode === "masterlist"
                        ? "This CSV will be used as the review master list instead of connector search."
                        : "Connector search will run, then this CSV will be merged before screening."}
                    </p>
                  )}
                </div>
              </div>

              {/* Column grid */}
              <div className="px-4 py-3">
                <p className="text-xs font-semibold text-muted uppercase tracking-wide mb-2">
                  Detected columns
                </p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                  {[...CSV_REQUIRED_COLS, ...CSV_EXPECTED_COLS].map((col) => {
                    const present = analysis.headers.includes(col)
                    const required = CSV_REQUIRED_COLS.includes(col)
                    return (
                      <div key={col} className="flex items-center gap-1.5">
                        <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                          present ? "bg-intent-success" : required ? "bg-intent-danger" : "bg-surface-4"
                        }`} />
                        <span className={`text-xs truncate ${
                          present ? "text-foreground" : required ? "text-intent-danger" : "text-muted"
                        }`}>
                          {col}
                          {required && !present && " *"}
                        </span>
                      </div>
                    )
                  })}
                </div>
                {analysis.missingExpected.length > 0 && analysis.valid && (
                  <p className="text-xs text-muted mt-2 leading-relaxed">
                    {analysis.missingExpected.length} optional column{analysis.missingExpected.length > 1 ? "s" : ""} not found - those fields will be blank in the review.
                  </p>
                )}
              </div>
            </>
          )}
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        className="hidden"
        onChange={(e) => handleAccept(e.target.files?.[0])}
      />
      </div>
    </TooltipProvider>
  )
}
