import { useCallback, useEffect, useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import {
  ChevronLeft,
  ChevronRight,
  Plus,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { type NotesStreamEvent } from "@/lib/api"
import type { HistoryEntry } from "@/lib/api"
import { historyFetchErrorMessage, historyQueryKey, useHistory } from "@/hooks/useHistory"
import { useNotesStream } from "@/hooks/useNotesStream"
import {
  TooltipProvider,
} from "@/components/ui/tooltip"
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog"
import { SidebarTooltip } from "@/components/sidebar/SidebarTooltip"
import { SidebarHeader } from "@/components/sidebar/SidebarHeader"
import { SidebarInProgressSection } from "@/components/sidebar/SidebarInProgressSection"
import { SidebarCompletedArchivedSection } from "@/components/sidebar/SidebarCompletedArchivedSection"
import { useRunSession } from "@/hooks/useRunSession"
export type { LiveRun, PhaseProgress } from "@/components/sidebar/types"

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
  width: number
  onWidthChange: (w: number) => void
  /** When true, renders the sidebar as a slide-in overlay drawer instead of a fixed column. */
  isMobile?: boolean
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

export function Sidebar({
  collapsed,
  onToggle,
  width,
  onWidthChange,
  isMobile = false,
}: SidebarProps) {
  const {
    liveRunForSidebar: liveRun,
    selectedRun,
    isViewingLiveRun: isLiveRunSelected,
    isRunning,
    handleSelectLiveRun: onSelectLiveRun,
    handleSelectHistory: onSelectHistory,
    handleNewReview: onNewReview,
    handleSidebarResumeLauncher: onResume,
    handleSidebarArchive: onArchive,
    handleSidebarRestore: onRestore,
    handleSidebarHideCompleted: onHideCompleted,
    handleSidebarRestoreCompleted: onRestoreCompleted,
    handleSidebarDelete: onDelete,
    handleCancel: onCancel,
    handleGoHome: onGoHome,
  } = useRunSession()

  const queryClient = useQueryClient()
  const selectedWorkflowId = selectedRun?.workflowId ?? null
  const {
    data: history = [],
    isLoading: loadingHistory,
    error: historyQueryError,
    refetch: refetchHistory,
  } = useHistory()
  const historyError = historyQueryError ? historyFetchErrorMessage(historyQueryError) : null
  const [openingId, setOpeningId] = useState<string | null>(null)
  const [resumingId, setResumingId] = useState<string | null>(null)
  const [archivingId, setArchivingId] = useState<string | null>(null)
  const [restoringId, setRestoringId] = useState<string | null>(null)
  const [completingId, setCompletingId] = useState<string | null>(null)
  const [restoringCompletedId, setRestoringCompletedId] = useState<string | null>(null)
  const [, setDeletingId] = useState<string | null>(null)
  const [deleteConfirmWorkflowId, setDeleteConfirmWorkflowId] =
    useState<string | null>(null)
  const [completedExpanded, setCompletedExpanded] = useState(false)
  const [archivedExpanded, setArchivedExpanded] = useState(false)
  const [openArchivedMenuId, setOpenArchivedMenuId] = useState<string | null>(null)
  const [wfIdCopied, setWfIdCopied] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const dragStartX = useRef(0)
  const dragStartWidth = useRef(0)

  // Notes: keyed by workflow_id. Seeded from history, updated via SSE.
  const [notes, setNotes] = useState<Record<string, string>>({})
  // Flash counter per workflow_id: incrementing forces NoteField to re-key and retrigger
  // the animation even when the same card receives rapid successive remote updates.
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

  // Seed notes map from history response (server is source of truth on load).
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

  // When a live run reaches terminal state, refresh history after a short
  // delay to pick up the final persisted status from the registry.
  useEffect(() => {
    if (
      liveRun?.status === "done" ||
      liveRun?.status === "error" ||
      liveRun?.status === "cancelled"
    ) {
      void refetchHistory()
      const timer = setTimeout(() => void refetchHistory(), 3000)
      return () => clearTimeout(timer)
    }
  }, [liveRun?.status, refetchHistory])

  // Drag-to-resize the sidebar
  useEffect(() => {
    if (!isDragging) return
    function onMouseMove(e: MouseEvent) {
      const delta = e.clientX - dragStartX.current
      const next = Math.max(200, Math.min(420, dragStartWidth.current + delta))
      onWidthChange(next)
    }
    function onMouseUp() {
      setIsDragging(false)
    }
    document.addEventListener("mousemove", onMouseMove)
    document.addEventListener("mouseup", onMouseUp)
    return () => {
      document.removeEventListener("mousemove", onMouseMove)
      document.removeEventListener("mouseup", onMouseUp)
    }
  }, [isDragging, onWidthChange])

  const liveRunHasHistoryRow = Boolean(
    liveRun && history.some((entry) => {
      if (liveRun.workflowId && entry.workflow_id === liveRun.workflowId) return true
      return Boolean(entry.live_run_id && entry.live_run_id === liveRun.runId)
    }),
  )
  // Render a standalone live card only during the brief bootstrap window where
  // the active run is not yet present in /api/history. Once present, decorate
  // that stable history row in-place to avoid sidebar reshuffles.
  const shouldShowStandaloneLiveCard = Boolean(liveRun && !liveRunHasHistoryRow)

  async function handleSelectHistory(entry: HistoryEntry) {
    setOpeningId(entry.workflow_id)
    // Close the mobile drawer when a run is selected
    if (isMobile) onToggle()
    try {
      await onSelectHistory(entry)
    } finally {
      setOpeningId(null)
    }
  }

  async function handleResumeLauncher(entry: HistoryEntry) {
    setResumingId(entry.workflow_id)
    try {
      await onResume(entry)
    } finally {
      setResumingId(null)
    }
  }

  async function handleArchiveConfirm(workflowId: string) {
    setArchivingId(workflowId)
    // Optimistic: move to archived immediately
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
  }

  async function handleRestoreConfirm(workflowId: string) {
    setRestoringId(workflowId)
    // Optimistic: move out of archived immediately
    optimisticHistoryUpdate((prev) =>
      prev.map((e) =>
        e.workflow_id === workflowId
          ? { ...e, is_archived: false, archived_at: null }
          : e,
      ),
    )
    setOpenArchivedMenuId((prev) => (prev === workflowId ? null : prev))
    try {
      await onRestore(workflowId)
    } finally {
      setRestoringId(null)
      void refetchHistory()
    }
  }

  async function handleCompleteConfirm(workflowId: string) {
    setCompletingId(workflowId)
    // Optimistic: move to completed section immediately
    optimisticHistoryUpdate((prev) =>
      prev.map((e) =>
        e.workflow_id === workflowId
          ? { ...e, is_completed_hidden: true, completed_hidden_at: new Date().toISOString() }
          : e,
      ),
    )
    try {
      await onHideCompleted(workflowId)
    } finally {
      setCompletingId(null)
      void refetchHistory()
    }
  }

  async function handleRestoreCompletedConfirm(workflowId: string) {
    setRestoringCompletedId(workflowId)
    // Optimistic: move out of completed section immediately
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
  }

  async function handleDeleteConfirm(workflowId: string) {
    setDeletingId(workflowId)
    // Optimistic: remove from list immediately
    optimisticHistoryUpdate((prev) => prev.filter((e) => e.workflow_id !== workflowId))
    try {
      await onDelete(workflowId)
    } finally {
      setDeletingId(null)
      void refetchHistory()
    }
  }

  function handleDragHandleMouseDown(e: React.MouseEvent) {
    e.preventDefault()
    dragStartX.current = e.clientX
    dragStartWidth.current = width
    setIsDragging(true)
  }

  const handleCopyWorkflowId = useCallback(async (id: string) => {
    await navigator.clipboard.writeText(id)
    setWfIdCopied(id)
    setTimeout(() => setWfIdCopied(null), 1500)
  }, [])

  const activeHistory = history.filter((entry) => !entry.is_archived)
  const completedHistory = activeHistory.filter((entry) => Boolean(entry.is_completed_hidden))
  const inProgressHistory = activeHistory.filter((entry) => !entry.is_completed_hidden)
  const archivedHistory = history.filter((entry) => Boolean(entry.is_archived))

  return (
    <TooltipProvider delayDuration={0}>
      {/* Backdrop: only shown on mobile when the drawer is open */}
      {isMobile && !collapsed && (
        <div
          className="fixed inset-0 z-40 bg-black/60"
          onClick={onToggle}
          aria-hidden
        />
      )}
      <aside
        className={cn(
          "fixed left-0 top-0 h-full bg-surface-0/90 border-r border-border/80 backdrop-blur-sm flex flex-col select-none overflow-hidden",
          isMobile
            ? cn(
                "z-50 w-72 transition-transform duration-200 ease-in-out",
                collapsed ? "-translate-x-full" : "translate-x-0",
              )
            : cn(
                "z-20",
                !isDragging && "transition-[width] duration-200 ease-in-out",
              ),
        )}
        style={isMobile
          ? { paddingTop: 'env(safe-area-inset-top)' }
          : { width: collapsed ? 56 : width, paddingTop: 'env(safe-area-inset-top)' }}
      >
        {/* Ambient violet glow -- gives the glass cards something to "float" against */}
        <div
          className="pointer-events-none absolute inset-0 z-0"
          aria-hidden
          style={{
            background: "var(--sidebar-ambient-gradient)",
          }}
        />

        <SidebarHeader
          collapsed={collapsed}
          isMobile={isMobile}
          onGoHome={onGoHome}
          onToggle={onToggle}
        />

        {/* New Review button */}
        <div className={cn("relative z-10 px-2.5 pt-3 pb-2 shrink-0", collapsed && "px-2")}>
          <SidebarTooltip label="New Review" collapsed={collapsed} side="right">
            <button
              onClick={() => { onNewReview(); if (isMobile) onToggle() }}
              className={cn(
                "sidebar-new-review-button flex items-center gap-2 rounded-lg transition-colors text-sm font-medium w-full",
                collapsed
                  ? "justify-center h-9 w-9 mx-auto"
                  : "px-3 py-2",
              )}
            >
              <Plus className="h-4 w-4 shrink-0" />
              {!collapsed && "New Review"}
            </button>
          </SidebarTooltip>
        </div>

        <nav className="flex-1 overflow-y-auto overflow-x-hidden px-2 pb-2 pt-1 relative z-10">
          <SidebarInProgressSection
            collapsed={collapsed}
            loadingHistory={loadingHistory}
            historyError={historyError}
            inProgressHistory={inProgressHistory}
            shouldShowStandaloneLiveCard={shouldShowStandaloneLiveCard}
            liveRun={liveRun}
            isLiveRunSelected={isLiveRunSelected}
            isRunning={isRunning}
            isMobile={Boolean(isMobile)}
            selectedWorkflowId={selectedWorkflowId}
            openingId={openingId}
            resumingId={resumingId}
            archivingId={archivingId}
            completingId={completingId}
            wfIdCopied={wfIdCopied}
            notes={notes}
            noteFlashCounters={noteFlashCounters}
            onRefresh={() => void refetchHistory()}
            onToggle={onToggle}
            onSelectLiveRun={onSelectLiveRun}
            onCancel={onCancel}
            onSelect={(row) => void handleSelectHistory(row)}
            onResume={(row) => void handleResumeLauncher(row)}
            onArchive={handleArchiveConfirm}
            onComplete={(id) => void handleCompleteConfirm(id)}
            onCopyWorkflowId={handleCopyWorkflowId}
            onNoteChange={(workflowId, val) =>
              setNotes((prev) => ({ ...prev, [workflowId]: val }))
            }
            sessionResume={onResume}
            sessionArchive={onArchive}
            sessionHideCompleted={onHideCompleted}
          />
        </nav>

        <SidebarCompletedArchivedSection
          completedHistory={completedHistory}
          archivedHistory={archivedHistory}
          completedExpanded={completedExpanded}
          archivedExpanded={archivedExpanded}
          collapsed={collapsed}
          selectedWorkflowId={selectedWorkflowId}
          wfIdCopied={wfIdCopied}
          archivingId={archivingId}
          restoringCompletedId={restoringCompletedId}
          completingId={completingId}
          restoringId={restoringId}
          openArchivedMenuId={openArchivedMenuId}
          onToggleCompleted={() => setCompletedExpanded((prev) => !prev)}
          onToggleArchived={() => setArchivedExpanded((prev) => !prev)}
          onSelect={(row) => void handleSelectHistory(row)}
          onCopyWorkflowId={handleCopyWorkflowId}
          onArchive={(id) => void handleArchiveConfirm(id)}
          onRestoreCompleted={(id) => void handleRestoreCompletedConfirm(id)}
          onComplete={(id) => void handleCompleteConfirm(id)}
          onRestore={(id) => void handleRestoreConfirm(id)}
          onToggleArchivedMenu={(id) =>
            setOpenArchivedMenuId((prev) => (prev === id ? null : id))
          }
          onDelete={(id) => {
            setOpenArchivedMenuId(null)
            setDeleteConfirmWorkflowId(id)
          }}
        />

        {/* Collapse toggle */}
        <button
          onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "relative z-10 flex items-center justify-center h-9 shrink-0 border-t border-border",
            "text-muted hover:text-foreground hover:bg-surface-2/50 transition-colors",
          )}
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </button>

        {/* Drag resize handle -- desktop only */}
        {!collapsed && !isMobile && (
          <div
            onMouseDown={handleDragHandleMouseDown}
            className={cn(
              "absolute top-0 right-0 w-1 h-full cursor-col-resize z-30",
              "hover:bg-intent-primary/40 transition-colors duration-150",
              isDragging && "bg-intent-primary/60",
            )}
          />
        )}
      </aside>

      <DeleteConfirmDialog
          open={deleteConfirmWorkflowId !== null}
          onOpenChange={(open) => !open && setDeleteConfirmWorkflowId(null)}
          workflowId={deleteConfirmWorkflowId}
          onConfirm={handleDeleteConfirm}
        />
    </TooltipProvider>
  )
}
