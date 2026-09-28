import { useCallback, useEffect, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import type { HistoryEntry, NotesStreamEvent } from "@/lib/api"
import { historyQueryKey } from "@/hooks/useHistory"
import { useNotesStream } from "@/hooks/useNotesStream"
import {
  isProsperoPendingStatus,
  isReviewPendingStatus,
  resolveRunStatus,
} from "@/lib/constants"
import { truncateTopic } from "@/components/sidebar/historyRowModel"
import type { LiveRun } from "@/components/sidebar/types"

export type SidebarLane = "in-progress" | "completed" | "archived"

export interface SidebarHistoryPartitions {
  prosperoPendingHistory: HistoryEntry[]
  inProgressHistory: HistoryEntry[]
  completedHistory: HistoryEntry[]
  archivedHistory: HistoryEntry[]
  visibleHistory: HistoryEntry[]
}

export const IN_PROGRESS_PINS_STORAGE_KEY = "sidebar-in-progress-pins"

/**
 * Which lane a history row belongs in. Archived and "Move to Completed" are
 * persisted flags. A finished run with neither flag goes to Completed unless the
 * user explicitly moved it back to In progress (a local pin).
 */
export function laneOf(entry: HistoryEntry, inProgressPins: ReadonlySet<string>): SidebarLane {
  if (entry.is_archived) return "archived"
  if (entry.is_completed_hidden) return "completed"
  const finished = resolveRunStatus(entry.status) === "done" && !entry.live_run_id
  if (finished && !inProgressPins.has(entry.workflow_id)) return "completed"
  return "in-progress"
}

/** Partition sidebar history into needs-input, in-progress, completed and archived lists. */
export function partitionHistory(
  history: HistoryEntry[],
  inProgressPins: ReadonlySet<string> = new Set(),
): SidebarHistoryPartitions {
  const completedHistory: HistoryEntry[] = []
  const archivedHistory: HistoryEntry[] = []
  const visibleHistory: HistoryEntry[] = []
  for (const entry of history) {
    const lane = laneOf(entry, inProgressPins)
    if (lane === "archived") archivedHistory.push(entry)
    else if (lane === "completed") completedHistory.push(entry)
    else visibleHistory.push(entry)
  }
  const needsInput = (entry: HistoryEntry) =>
    isProsperoPendingStatus(entry.status) || isReviewPendingStatus(entry.status)

  return {
    prosperoPendingHistory: visibleHistory.filter(needsInput),
    inProgressHistory: visibleHistory.filter((entry) => !needsInput(entry)),
    completedHistory,
    archivedHistory,
    visibleHistory,
  }
}

/** True when the active live run is not yet present in /api/history. */
export function computeShouldShowStandaloneLiveCard(
  liveRun: LiveRun | null | undefined,
  history: HistoryEntry[],
): boolean {
  const liveRunHasHistoryRow = Boolean(
    liveRun
    && history.some((entry) => {
      if (liveRun.workflowId && entry.workflow_id === liveRun.workflowId) return true
      return Boolean(entry.live_run_id && entry.live_run_id === liveRun.runId)
    }),
  )
  return Boolean(liveRun && !liveRunHasHistoryRow)
}

function readPins(): Set<string> {
  try {
    const raw = localStorage.getItem(IN_PROGRESS_PINS_STORAGE_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return new Set(Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string") : [])
  } catch {
    return new Set()
  }
}

function writePins(pins: ReadonlySet<string>) {
  try {
    localStorage.setItem(IN_PROGRESS_PINS_STORAGE_KEY, JSON.stringify([...pins]))
  } catch {
    // Storage full or disabled; the pin still applies for this session.
  }
}

interface LaneFlags {
  archived: boolean
  completedHidden: boolean
  pinned: boolean
}

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback
}

export interface UseSidebarRunsOptions {
  history: HistoryEntry[]
  refetchHistory: () => Promise<unknown> | void
  liveRun: LiveRun | null
  onSelectHistory: (entry: HistoryEntry) => Promise<void>
  onResume: (entry: HistoryEntry) => Promise<void>
  onArchive: (workflowId: string) => Promise<void>
  onRestore: (workflowId: string) => Promise<void>
  onHideCompleted: (workflowId: string) => Promise<void>
  onRestoreCompleted: (workflowId: string) => Promise<void>
  onDelete: (workflowId: string) => Promise<void>
  isMobile?: boolean
  onToggle?: () => void
}

export function useSidebarRuns({
  history,
  refetchHistory,
  liveRun,
  onSelectHistory,
  onResume,
  onArchive,
  onRestore,
  onHideCompleted,
  onRestoreCompleted,
  onDelete,
  isMobile = false,
  onToggle,
}: UseSidebarRunsOptions) {
  const queryClient = useQueryClient()

  const [openingId, setOpeningId] = useState<string | null>(null)
  const [resumingId, setResumingId] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [deleteConfirmWorkflowId, setDeleteConfirmWorkflowId] = useState<string | null>(null)
  const [inProgressPins, setInProgressPins] = useState<Set<string>>(readPins)

  const [notes, setNotes] = useState<Record<string, string>>({})
  const [noteFlashCounters, setNoteFlashCounters] = useState<Record<string, number>>({})

  const setPinned = useCallback((workflowId: string, pinned: boolean) => {
    setInProgressPins((prev) => {
      if (prev.has(workflowId) === pinned) return prev
      const next = new Set(prev)
      if (pinned) next.add(workflowId)
      else next.delete(workflowId)
      writePins(next)
      return next
    })
  }, [])

  const optimisticHistoryUpdate = useCallback(
    (updater: (prev: HistoryEntry[]) => HistoryEntry[]) => {
      queryClient.setQueryData<HistoryEntry[]>(historyQueryKey(), (prev) =>
        updater(prev ?? []),
      )
    },
    [queryClient],
  )

  const handleNotesStreamMessage = useCallback((data: NotesStreamEvent) => {
    setNotes((prev) => ({ ...prev, [data.workflow_id]: data.note }))
    setNoteFlashCounters((prev) => ({
      ...prev,
      [data.workflow_id]: (prev[data.workflow_id] ?? 0) + 1,
    }))
  }, [])

  useNotesStream(handleNotesStreamMessage)

  useEffect(() => {
    if (!history.length) return
    setNotes((prev) => {
      const next = { ...prev }
      for (const entry of history) {
        if (entry.notes != null) next[entry.workflow_id] = entry.notes
      }
      return next
    })
  }, [history])

  useEffect(() => {
    if (
      liveRun?.status === "done"
      || liveRun?.status === "error"
      || liveRun?.status === "cancelled"
    ) {
      void refetchHistory()
      const timer = setTimeout(() => void refetchHistory(), 3000)
      return () => clearTimeout(timer)
    }
  }, [liveRun?.status, refetchHistory])

  const handleOpen = useCallback(
    async (entry: HistoryEntry) => {
      setOpeningId(entry.workflow_id)
      if (isMobile) onToggle?.()
      try {
        await onSelectHistory(entry)
      } finally {
        setOpeningId(null)
      }
    },
    [isMobile, onSelectHistory, onToggle],
  )

  const handleResume = useCallback(
    async (entry: HistoryEntry) => {
      setResumingId(entry.workflow_id)
      try {
        await onResume(entry)
      } finally {
        setResumingId(null)
      }
    },
    [onResume],
  )

  const applyLaneFlags = useCallback(
    async (workflowId: string, from: LaneFlags, to: LaneFlags) => {
      const now = new Date().toISOString()
      optimisticHistoryUpdate((prev) =>
        prev.map((e) =>
          e.workflow_id === workflowId
            ? {
                ...e,
                is_archived: to.archived,
                archived_at: to.archived ? (e.archived_at ?? now) : null,
                is_completed_hidden: !to.archived && to.completedHidden,
                completed_hidden_at:
                  !to.archived && to.completedHidden ? (e.completed_hidden_at ?? now) : null,
              }
            : e,
        ),
      )
      setPinned(workflowId, to.pinned)
      try {
        if (to.archived) {
          if (!from.archived) await onArchive(workflowId)
        } else if (to.completedHidden) {
          if (from.archived || !from.completedHidden) await onHideCompleted(workflowId)
        } else if (from.archived) {
          await onRestore(workflowId)
        } else if (from.completedHidden) {
          await onRestoreCompleted(workflowId)
        }
      } catch (err) {
        setPinned(workflowId, from.pinned)
        throw err
      }
    },
    [onArchive, onHideCompleted, onRestore, onRestoreCompleted, optimisticHistoryUpdate, setPinned],
  )

  const moveWithUndo = useCallback(
    async (
      workflowId: string,
      target: (from: LaneFlags) => LaneFlags,
      describe: (topic: string) => string,
      fallbackTopic?: string,
    ) => {
      const entry = history.find((e) => e.workflow_id === workflowId)
      const from: LaneFlags = {
        archived: Boolean(entry?.is_archived),
        completedHidden: Boolean(entry?.is_completed_hidden),
        pinned: inProgressPins.has(workflowId),
      }
      const to = target(from)
      const topic = `"${truncateTopic(entry?.topic ?? fallbackTopic ?? workflowId, 40)}"`
      setBusyId(workflowId)
      try {
        await applyLaneFlags(workflowId, from, to)
        toast(describe(topic), {
          action: {
            label: "Undo",
            onClick: () => {
              void applyLaneFlags(workflowId, to, from)
                .catch((err: unknown) => {
                  toast.error(errorMessage(err, "Couldn't undo that change"))
                })
                .finally(() => void refetchHistory())
            },
          },
        })
      } catch (err) {
        toast.error(errorMessage(err, "Couldn't move the review"))
      } finally {
        setBusyId(null)
        void refetchHistory()
      }
    },
    [applyLaneFlags, history, inProgressPins, refetchHistory],
  )

  const handleArchive = useCallback(
    (workflowId: string, fallbackTopic?: string) =>
      moveWithUndo(
        workflowId,
        (from) => ({ archived: true, completedHidden: false, pinned: from.pinned }),
        (topic) => `Archived ${topic}`,
        fallbackTopic,
      ),
    [moveWithUndo],
  )

  const handleMoveToCompleted = useCallback(
    (workflowId: string) =>
      moveWithUndo(
        workflowId,
        () => ({ archived: false, completedHidden: true, pinned: false }),
        (topic) => `Moved ${topic} to Completed`,
      ),
    [moveWithUndo],
  )

  const handleMoveToInProgress = useCallback(
    (workflowId: string) =>
      moveWithUndo(
        workflowId,
        () => ({ archived: false, completedHidden: false, pinned: true }),
        (topic) => `Moved ${topic} to In progress`,
      ),
    [moveWithUndo],
  )

  const handleDeleteRequest = useCallback((workflowId: string) => {
    setDeleteConfirmWorkflowId(workflowId)
  }, [])

  const handleDeleteConfirm = useCallback(
    async (workflowId: string) => {
      await onDelete(workflowId)
      optimisticHistoryUpdate((prev) => prev.filter((e) => e.workflow_id !== workflowId))
      setPinned(workflowId, false)
      void refetchHistory()
    },
    [onDelete, optimisticHistoryUpdate, refetchHistory, setPinned],
  )

  const partitions = partitionHistory(history, inProgressPins)
  const shouldShowStandaloneLiveCard = computeShouldShowStandaloneLiveCard(liveRun, history)

  return {
    ...partitions,
    shouldShowStandaloneLiveCard,
    openingId,
    resumingId,
    busyId,
    deleteConfirmWorkflowId,
    setDeleteConfirmWorkflowId,
    notes,
    setNotes,
    noteFlashCounters,
    handleOpen,
    handleResume,
    handleArchive,
    handleMoveToCompleted,
    handleMoveToInProgress,
    handleDeleteRequest,
    handleDeleteConfirm,
  }
}
