import { useCallback, useEffect, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import type { HistoryEntry, NotesStreamEvent } from "@/lib/api"
import { historyQueryKey } from "@/hooks/useHistory"
import { useNotesStream } from "@/hooks/useNotesStream"
import { isProsperoPendingStatus } from "@/lib/constants"
import type { LiveRun } from "@/components/sidebar/types"

export interface SidebarHistoryPartitions {
  prosperoPendingHistory: HistoryEntry[]
  inProgressHistory: HistoryEntry[]
  completedHistory: HistoryEntry[]
  archivedHistory: HistoryEntry[]
  visibleHistory: HistoryEntry[]
}

/** Partition sidebar history into in-progress, completed, archived, and PROSPERO-pending lists. */
export function partitionHistory(history: HistoryEntry[]): SidebarHistoryPartitions {
  const activeHistory = history.filter((entry) => !entry.is_archived)
  const completedHistory = activeHistory.filter((entry) => Boolean(entry.is_completed_hidden))
  const visibleHistory = activeHistory.filter((entry) => !entry.is_completed_hidden)
  const prosperoPendingHistory = visibleHistory.filter((entry) =>
    isProsperoPendingStatus(entry.status),
  )
  const inProgressHistory = visibleHistory.filter(
    (entry) => !isProsperoPendingStatus(entry.status),
  )
  const archivedHistory = history.filter((entry) => Boolean(entry.is_archived))

  return {
    prosperoPendingHistory,
    inProgressHistory,
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
  onArchivedMenuClose?: () => void
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
  onArchivedMenuClose,
}: UseSidebarRunsOptions) {
  const queryClient = useQueryClient()

  const [openingId, setOpeningId] = useState<string | null>(null)
  const [resumingId, setResumingId] = useState<string | null>(null)
  const [archivingId, setArchivingId] = useState<string | null>(null)
  const [restoringId, setRestoringId] = useState<string | null>(null)
  const [completingId, setCompletingId] = useState<string | null>(null)
  const [restoringCompletedId, setRestoringCompletedId] = useState<string | null>(null)
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

  const handleArchive = useCallback(
    async (workflowId: string) => {
      setArchivingId(workflowId)
      optimisticHistoryUpdate((prev) =>
        prev.map((e) =>
          e.workflow_id === workflowId
            ? { ...e, is_archived: true, archived_at: new Date().toISOString() }
            : e,
        ),
      )
      try {
        await onArchive(workflowId)
      } finally {
        setArchivingId(null)
        void refetchHistory()
      }
    },
    [onArchive, optimisticHistoryUpdate, refetchHistory],
  )

  const handleRestore = useCallback(
    async (workflowId: string) => {
      setRestoringId(workflowId)
      optimisticHistoryUpdate((prev) =>
        prev.map((e) =>
          e.workflow_id === workflowId
            ? { ...e, is_archived: false, archived_at: null }
            : e,
        ),
      )
      onArchivedMenuClose?.()
      try {
        await onRestore(workflowId)
      } finally {
        setRestoringId(null)
        void refetchHistory()
      }
    },
    [onArchivedMenuClose, onRestore, optimisticHistoryUpdate, refetchHistory],
  )

  const handleHideCompleted = useCallback(
    async (workflowId: string) => {
      setCompletingId(workflowId)
      optimisticHistoryUpdate((prev) =>
        prev.map((e) =>
          e.workflow_id === workflowId
            ? {
                ...e,
                is_completed_hidden: true,
                completed_hidden_at: new Date().toISOString(),
              }
            : e,
        ),
      )
      try {
        await onHideCompleted(workflowId)
      } finally {
        setCompletingId(null)
        void refetchHistory()
      }
    },
    [onHideCompleted, optimisticHistoryUpdate, refetchHistory],
  )

  const handleRestoreCompleted = useCallback(
    async (workflowId: string) => {
      setRestoringCompletedId(workflowId)
      optimisticHistoryUpdate((prev) =>
        prev.map((e) =>
          e.workflow_id === workflowId
            ? { ...e, is_completed_hidden: false, completed_hidden_at: null }
            : e,
        ),
      )
      try {
        await onRestoreCompleted(workflowId)
      } finally {
        setRestoringCompletedId(null)
        void refetchHistory()
      }
    },
    [onRestoreCompleted, optimisticHistoryUpdate, refetchHistory],
  )

  const handleDeleteRequest = useCallback(
    (workflowId: string) => {
      onArchivedMenuClose?.()
      setDeleteConfirmWorkflowId(workflowId)
    },
    [onArchivedMenuClose],
  )

  const handleDeleteConfirm = useCallback(
    async (workflowId: string) => {
      optimisticHistoryUpdate((prev) => prev.filter((e) => e.workflow_id !== workflowId))
      try {
        await onDelete(workflowId)
      } finally {
        void refetchHistory()
      }
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
    archivingId,
    restoringId,
    completingId,
    restoringCompletedId,
    deleteConfirmWorkflowId,
    setDeleteConfirmWorkflowId,
    notes,
    setNotes,
    noteFlashCounters,
    handleOpen,
    handleResume,
    handleArchive,
    handleRestore,
    handleHideCompleted,
    handleRestoreCompleted,
    handleDeleteRequest,
    handleDeleteConfirm,
  }
}
