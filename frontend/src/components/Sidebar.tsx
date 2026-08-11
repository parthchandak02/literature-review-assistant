import { useCallback, useEffect, useRef, useState } from "react"
import {
  ChevronLeft,
  ChevronRight,
  Plus,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { historyFetchErrorMessage, useHistory } from "@/hooks/useHistory"
import { useSidebarRuns } from "@/hooks/useSidebarRuns"
import {
  TooltipProvider,
} from "@/components/ui/tooltip"
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog"
import { SidebarTooltip } from "@/components/sidebar/SidebarTooltip"
import { SidebarHeader } from "@/components/sidebar/SidebarHeader"
import { SidebarInProgressSection } from "@/components/sidebar/SidebarInProgressSection"
import { SidebarCompletedArchivedSection } from "@/components/sidebar/SidebarCompletedArchivedSection"
import { useRunSessionActions, useRunSessionState } from "@/hooks/useRunSession"
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
  } = useRunSessionState()
  const {
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
  } = useRunSessionActions()

  const selectedWorkflowId = selectedRun?.workflowId ?? null
  const {
    data: history = [],
    isLoading: loadingHistory,
    error: historyQueryError,
    refetch: refetchHistory,
  } = useHistory()
  const historyError = historyQueryError ? historyFetchErrorMessage(historyQueryError) : null

  const [completedExpanded, setCompletedExpanded] = useState(false)
  const [archivedExpanded, setArchivedExpanded] = useState(false)
  const [openArchivedMenuId, setOpenArchivedMenuId] = useState<string | null>(null)
  const [wfIdCopied, setWfIdCopied] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const dragStartX = useRef(0)
  const dragStartWidth = useRef(0)

  const closeArchivedMenu = useCallback(() => {
    setOpenArchivedMenuId(null)
  }, [])

  const {
    prosperoPendingHistory,
    inProgressHistory,
    completedHistory,
    archivedHistory,
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
  } = useSidebarRuns({
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
    isMobile,
    onToggle,
    onArchivedMenuClose: closeArchivedMenu,
  })

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
            prosperoPendingHistory={prosperoPendingHistory}
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
            onSelect={(row) => void handleOpen(row)}
            onResume={(row) => void handleResume(row)}
            onArchive={handleArchive}
            onComplete={(id) => void handleHideCompleted(id)}
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
          onSelect={(row) => void handleOpen(row)}
          onCopyWorkflowId={handleCopyWorkflowId}
          onArchive={(id) => void handleArchive(id)}
          onRestoreCompleted={(id) => void handleRestoreCompleted(id)}
          onComplete={(id) => void handleHideCompleted(id)}
          onRestore={(id) => void handleRestore(id)}
          onToggleArchivedMenu={(id) =>
            setOpenArchivedMenuId((prev) => (prev === id ? null : id))
          }
          onDelete={handleDeleteRequest}
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
