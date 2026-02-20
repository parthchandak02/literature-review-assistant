import { useState, useEffect, useRef } from "react"
import { ChevronDown, Clock, RotateCcw, X } from "lucide-react"
import { RunForm } from "@/components/RunForm"
import { fetchHistory, fetchRunConfig } from "@/lib/api"
import type { HistoryEntry, RunRequest } from "@/lib/api"

interface SetupViewProps {
  defaultReviewYaml: string
  onSubmit: (req: RunRequest) => Promise<void>
  disabled: boolean
}

function formatDate(iso: string): string {
  if (!iso) return ""
  try {
    const d = new Date(iso)
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
  } catch {
    return iso.slice(0, 10)
  }
}

export function SetupView({ defaultReviewYaml, onSubmit, disabled }: SetupViewProps) {
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [loadYaml, setLoadYaml] = useState<string | null>(null)
  const [loadingConfig, setLoadingConfig] = useState<string | null>(null)  // workflowId being fetched
  const [loadError, setLoadError] = useState<string | null>(null)
  const [showDropdown, setShowDropdown] = useState(false)
  const [loadedRunTopic, setLoadedRunTopic] = useState<string | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Fetch history once when SetupView mounts so we can list past runs
  useEffect(() => {
    fetchHistory().then(setHistory).catch(() => setHistory([]))
  }, [])

  // Close dropdown on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false)
      }
    }
    if (showDropdown) document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [showDropdown])

  async function handleLoadRun(entry: HistoryEntry) {
    setShowDropdown(false)
    setLoadError(null)
    setLoadingConfig(entry.workflow_id)
    try {
      const yaml = await fetchRunConfig(entry.workflow_id)
      if (!yaml) {
        setLoadError(
          `Config not saved for "${entry.topic}". Only runs started after this feature was added can be loaded.`
        )
        return
      }
      setLoadYaml(yaml)
      setLoadedRunTopic(entry.topic)
    } catch {
      setLoadError("Failed to load config for that run.")
    } finally {
      setLoadingConfig(null)
    }
  }

  function clearLoaded() {
    setLoadYaml(null)
    setLoadedRunTopic(null)
    setLoadError(null)
  }

  const recentRuns = history.filter((h) => h.status === "completed").slice(0, 10)

  return (
    <div className="max-w-2xl mx-auto pt-2 pb-16">
      {/* Header */}
      <div className="mb-5">
        <h2 className="text-base font-semibold text-zinc-200">New Systematic Review</h2>
        <p className="text-xs text-zinc-500 mt-1 leading-relaxed">
          Configure your review topic, search strategy, and criteria below.
        </p>
      </div>

      {/* Load from past run */}
      {recentRuns.length > 0 && (
        <div className="relative mb-4" ref={dropdownRef}>
          <div className="flex items-center gap-2">
            {loadedRunTopic ? (
              <div className="flex items-center gap-2 text-xs text-violet-300 bg-violet-600/15 border border-violet-500/30 rounded-lg px-3 py-1.5">
                <RotateCcw className="h-3 w-3 flex-shrink-0" />
                <span className="truncate max-w-[280px]">
                  Loaded config from: &quot;{loadedRunTopic}&quot;
                </span>
                <button
                  type="button"
                  onClick={clearLoaded}
                  className="ml-1 text-violet-400 hover:text-violet-200 transition-colors flex-shrink-0"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setShowDropdown((v) => !v)}
                disabled={!!loadingConfig}
                className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
              >
                <RotateCcw className={`h-3.5 w-3.5 ${loadingConfig ? "animate-spin" : ""}`} />
                {loadingConfig ? "Loading config..." : "Load config from a past run"}
                <ChevronDown className={`h-3 w-3 transition-transform ${showDropdown ? "" : "-rotate-90"}`} />
              </button>
            )}
          </div>

          {/* Dropdown */}
          {showDropdown && (
            <div className="absolute left-0 top-full mt-1 z-20 w-[420px] max-h-[280px] overflow-y-auto bg-zinc-900 border border-zinc-700 rounded-xl shadow-xl">
              <div className="px-3 py-2 border-b border-zinc-800">
                <p className="text-xs text-zinc-500">Select a completed run to reuse its configuration</p>
              </div>
              {recentRuns.map((entry) => (
                <button
                  key={entry.workflow_id}
                  type="button"
                  onClick={() => void handleLoadRun(entry)}
                  className="w-full flex items-start gap-2.5 px-3 py-2.5 hover:bg-zinc-800/60 transition-colors text-left border-b border-zinc-800/50 last:border-0"
                >
                  <Clock className="h-3.5 w-3.5 text-zinc-600 mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-zinc-200 truncate leading-snug">{entry.topic}</p>
                    <p className="text-xs text-zinc-600 mt-0.5">{formatDate(entry.created_at)}</p>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Load error */}
      {loadError && (
        <div className="mb-4 flex items-start gap-2 text-xs text-amber-400/80 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2.5">
          <span className="leading-relaxed">{loadError}</span>
          <button
            type="button"
            onClick={() => setLoadError(null)}
            className="ml-auto text-amber-500/60 hover:text-amber-400 transition-colors flex-shrink-0"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      <RunForm
        defaultReviewYaml={defaultReviewYaml}
        onSubmit={onSubmit}
        disabled={disabled}
        loadYaml={loadYaml}
      />
    </div>
  )
}
