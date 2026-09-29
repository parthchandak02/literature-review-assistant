import { isConfigGenerationStalled } from "@/lib/configGenerationStall"
import { useCallback, useEffect, useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { setHistoryLane } from "@/lib/api"
import type { HistoryEntry, LaneOverride, NotesStreamEvent } from "@/lib/api"
import { historyQueryKey } from "@/hooks/useHistory"
import { useNotesStream } from "@/hooks/useNotesStream"
import {
  isProsperoPendingStatus,
  isReviewPendingStatus,
  resolveRunStatus,
} from "@/lib/constants"
import { truncateTopic } from "@/components/sidebar/historyRowModel"
import type { LaneChangeOptions, LiveRun } from "@/components/sidebar/types"

export type SidebarLane = "in-progress" | "completed" | "archived"

export interface SidebarHistoryPartitions {
  prosperoPendingHistory: HistoryEntry[]
  inProgressHistory: HistoryEntry[]
  completedHistory: HistoryEntry[]
  archivedHistory: HistoryEntry[]
  visibleHistory: HistoryEntry[]
}

/** Legacy per-browser "Move to In progress" pins, migrated once to the server `lane_override`. */
export const IN_PROGRESS_PINS_STORAGE_KEY = "sidebar-in-progress-pins"

/** Server lane pin; rows from older backends only carry `is_completed_hidden`. */
export function laneOverrideOf(entry: HistoryEntry): LaneOverride | null {
  if (entry.is_completed_hidden || entry.lane_override === "completed") return "completed"
  return entry.lane_override === "in_progress" ? "in_progress" : null
}

/**
 * Which lane a history row belongs in. Archived and the lane pin are persisted
 * in the registry. A finished run with no pin goes to Completed.
 */
export function laneOf(entry: HistoryEntry): SidebarLane {
  if (entry.is_archived) return "archived"
  const override = laneOverrideOf(entry)
  if (override === "completed") return "completed"
  if (override === "in_progress") return "in-progress"
  const finished = resolveRunStatus(entry.status) === "done" && !entry.live_run_id
  return finished ? "completed" : "in-progress"
}

/** Partition sidebar history into needs-input, in-progress, completed and archived lists. */
export function partitionHistory(history: HistoryEntry[]): SidebarHistoryPartitions {
  const completedHistory: HistoryEntry[] = []
  const archivedHistory: HistoryEntry[] = []
  const visibleHistory: HistoryEntry[] = []
  for (const entry of history) {
    const lane = laneOf(entry)
    if (lane === "archived") archivedHistory.push(entry)
    else if (lane === "completed") completedHistory.push(entry)
    else visibleHistory.push(entry)
  }
  // A config still generating is work in progress; once it has stalled it needs the user.
  const needsInput = (entry: HistoryEntry) =>
    (isProsperoPendingStatus(entry.status) && entry.status.toLowerCase() !== "config_generating")
    || isReviewPendingStatus(entry.status)
    || isConfigGenerationStalled(entry, false)

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

function readLegacyPins(): string[] {
  try {
    const raw = localStorage.getItem(IN_PROGRESS_PINS_STORAGE_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string") : []
  } catch {
    return []
  }
}

function writeLegacyPins(pins: string[]) {
  try {
    if (pins.length) localStorage.setItem(IN_PROGRESS_PINS_STORAGE_KEY, JSON.stringify(pins))
    else localStorage.removeItem(IN_PROGRESS_PINS_STORAGE_KEY)
  } catch {
    // Storage disabled; nothing left to migrate.
  }
}

/**
 * Push legacy localStorage pins to the server once, then clear them. A server-side pin wins,
 * pins for reviews no longer in history are dropped, and failed pushes stay for the next load.
 * Returns the workflow ids that were pinned to In progress.
 */
export async function migrateLegacyInProgressPins(
  history: HistoryEntry[],
  setLane: (workflowId: string, lane: LaneOverride | null) => Promise<void> = setHistoryLane,
): Promise<string[]> {
  const pins = readLegacyPins()
  if (!pins.length) return []
  const byId = new Map(history.map((e) => [e.workflow_id, e]))
  const pending = pins.filter((id) => {
    const entry = byId.get(id)
    return entry !== undefined && laneOverrideOf(entry) === null
  })
  const results = await Promise.allSettled(pending.map((id) => setLane(id, "in_progress")))
  writeLegacyPins(pending.filter((_, i) => results[i].status === "rejected"))
  return pending.filter((_, i) => results[i].status === "fulfilled")
}

interface LaneFlags {
  archived: boolean
  lane: LaneOverride | null
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
  onRestore: (workflowId: string, options?: LaneChangeOptions) => Promise<void>
  onHideCompleted: (workflowId: string, options?: LaneChangeOptions) => Promise<void>
  onRestoreCompleted: (workflowId: string, options?: LaneChangeOptions) => Promise<void>
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

  const [notes, setNotes] = useState<Record<string, string>>({})
  const [noteFlashCounters, setNoteFlashCounters] = useState<Record<string, number>>({})

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

  const legacyPinsMigratedRef = useRef(false)
  useEffect(() => {
    if (legacyPinsMigratedRef.current || !history.length) return
    legacyPinsMigratedRef.current = true
    void migrateLegacyInProgressPins(history).then((pinned) => {
      if (!pinned.length) return
      const ids = new Set(pinned)
      optimisticHistoryUpdate((prev) =>
        prev.map((e) => (ids.has(e.workflow_id) ? { ...e, lane_override: "in_progress" } : e)),
      )
      void refetchHistory()
    })
  }, [history, optimisticHistoryUpdate, refetchHistory])

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
    async (workflowId: string, from: LaneFlags, to: LaneFlags, options: { undo?: boolean } = {}) => {
      const now = new Date().toISOString()
      const completed = !to.archived && to.lane === "completed"
      optimisticHistoryUpdate((prev) =>
        prev.map((e) =>
          e.workflow_id === workflowId
            ? {
                ...e,
                is_archived: to.archived,
                archived_at: to.archived ? (e.archived_at ?? now) : null,
                is_completed_hidden: completed,
                completed_hidden_at: completed ? (e.completed_hidden_at ?? now) : null,
                lane_override: to.lane,
              }
            : e,
        ),
      )
      const { undo } = options
      if (to.archived) {
        if (!from.archived) await onArchive(workflowId)
      } else if (from.archived) {
        await onRestore(workflowId, { undo, lane: to.lane })
      } else if (to.lane === "completed") {
        if (from.lane !== "completed") await onHideCompleted(workflowId, { undo })
      } else if (to.lane !== from.lane) {
        await onRestoreCompleted(workflowId, { undo, lane: to.lane })
      }
    },
    [onArchive, onHideCompleted, onRestore, onRestoreCompleted, optimisticHistoryUpdate],
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
        lane: entry ? laneOverrideOf(entry) : null,
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
              void applyLaneFlags(workflowId, to, from, { undo: true })
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
    [applyLaneFlags, history, refetchHistory],
  )

  const handleArchive = useCallback(
    (workflowId: string, fallbackTopic?: string) =>
      moveWithUndo(
        workflowId,
        (from) => ({ archived: true, lane: from.lane === "in_progress" ? "in_progress" : null }),
        (topic) => `Archived ${topic}`,
        fallbackTopic,
      ),
    [moveWithUndo],
  )

  const handleMoveToCompleted = useCallback(
    (workflowId: string) =>
      moveWithUndo(
        workflowId,
        () => ({ archived: false, lane: "completed" }),
        (topic) => `Moved ${topic} to Completed`,
      ),
    [moveWithUndo],
  )

  const handleMoveToInProgress = useCallback(
    (workflowId: string) =>
      moveWithUndo(
        workflowId,
        () => ({ archived: false, lane: "in_progress" }),
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
      void refetchHistory()
    },
    [onDelete, optimisticHistoryUpdate, refetchHistory],
  )

  const partitions = partitionHistory(history)
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
