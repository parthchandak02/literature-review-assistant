import { useCallback, useEffect, useMemo, useState } from "react"
import { CheckCircle, Circle, Loader2 } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { fetchWorkflowEvents } from "@/lib/api"
import { RESUME_PHASE_ORDER, PHASE_LABELS } from "@/lib/constants"
import type { HistoryEntry, ReviewEvent } from "@/lib/api"
import { cn } from "@/lib/utils"

function buildPhaseDoneSet(events: ReviewEvent[]): Set<string> {
  const done = new Set<string>()
  for (const ev of events) {
    if (ev.type === "phase_done") {
      done.add(ev.phase)
    }
  }
  // Only infer phase_done when run completed successfully. For cancelled/error
  // runs, a phase with phase_start but no phase_done did NOT complete.
  const terminalEv = events.find(
    (e) => e.type === "done" || e.type === "error" || e.type === "cancelled",
  )
  if (terminalEv?.type === "done") {
    for (const phase of RESUME_PHASE_ORDER) {
      const hasStart = events.some(
        (e) => e.type === "phase_start" && e.phase === phase,
      )
      if (hasStart) done.add(phase)
    }
  }
  return done
}

export interface ResumeFromPhaseModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  entry: HistoryEntry
  onResume: (fromPhase?: string) => Promise<void>
}

export function ResumeFromPhaseModal({
  open,
  onOpenChange,
  entry,
  onResume,
}: ResumeFromPhaseModalProps) {
  const [events, setEvents] = useState<ReviewEvent[]>([])
  const [loading, setLoading] = useState(false)
  const [resuming, setResuming] = useState<string | null>(null)

  const phaseDone = useMemo(
    () => buildPhaseDoneSet(events),
    [events],
  )

  useEffect(() => {
    if (!open || !entry.workflow_id) return
    setLoading(true)
    fetchWorkflowEvents(entry.workflow_id)
      .then(setEvents)
      .catch(() => setEvents([]))
      .finally(() => setLoading(false))
  }, [open, entry.workflow_id])

  const canResumeFrom = useCallback(
    (phase: string) => {
      const idx = RESUME_PHASE_ORDER.indexOf(phase)
      if (idx <= 0) return true
      for (let i = 0; i < idx; i++) {
        if (!phaseDone.has(RESUME_PHASE_ORDER[i])) return false
      }
      return true
    },
    [phaseDone],
  )

  const firstIncomplete = useMemo(() => {
    for (const phase of RESUME_PHASE_ORDER) {
      if (!phaseDone.has(phase)) return phase
    }
    return null
  }, [phaseDone])

  async function handleResume(fromPhase?: string) {
    if (resuming) return
    setResuming(fromPhase ?? "default")
    try {
      await onResume(fromPhase)
      onOpenChange(false)
    } finally {
      setResuming(null)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Resume from phase</DialogTitle>
          <DialogDescription>
            Choose where to resume this run. Resuming from a phase will re-run
            that phase and all later phases.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-8 gap-2 text-zinc-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="text-sm">Loading phase status...</span>
          </div>
        ) : (
          <div className="space-y-2 py-2">
            {firstIncomplete && (
              <button
                onClick={() => void handleResume()}
                disabled={resuming !== null}
                className={cn(
                  "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left",
                  "bg-violet-500/20 hover:bg-violet-500/30 border border-violet-500/40",
                  "text-violet-300 font-medium transition-colors",
                  resuming === "default" && "opacity-70 cursor-wait",
                )}
              >
                {resuming === "default" ? (
                  <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
                ) : (
                  <Circle className="h-4 w-4 shrink-0" />
                )}
                <span>
                  Resume from first incomplete ({PHASE_LABELS[firstIncomplete] ?? firstIncomplete})
                </span>
              </button>
            )}

            <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mt-3 mb-1.5 px-1">
              Or resume from a specific phase
            </div>

            {RESUME_PHASE_ORDER.map((phase) => {
              const done = phaseDone.has(phase)
              const enabled = canResumeFrom(phase)
              const label = PHASE_LABELS[phase] ?? phase
              const isResumingThis = resuming === phase

              return (
                <button
                  key={phase}
                  onClick={() => (enabled ? void handleResume(phase) : undefined)}
                  disabled={!enabled || resuming !== null}
                  className={cn(
                    "w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left text-sm transition-colors",
                    enabled
                      ? "hover:bg-zinc-800 text-zinc-200"
                      : "opacity-50 cursor-not-allowed text-zinc-500",
                    isResumingThis && "opacity-70 cursor-wait",
                  )}
                >
                  {done ? (
                    <CheckCircle className="h-4 w-4 shrink-0 text-emerald-500" />
                  ) : (
                    <Circle className="h-4 w-4 shrink-0 text-zinc-600" />
                  )}
                  {isResumingThis ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : null}
                  <span>{label}</span>
                </button>
              )
            })}
          </div>
        )}

        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={resuming !== null}
          >
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
