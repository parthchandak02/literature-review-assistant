import { useCallback, useEffect, useRef, useState } from "react"
import { ChevronLeft, ChevronRight, Plus } from "lucide-react"
import { cn } from "@/lib/utils"
import {
  historyFetchErrorMessage,
  resolveHistoryRefetchInterval,
  useHistory,
} from "@/hooks/useHistory"
import { useSidebarRuns } from "@/hooks/useSidebarRuns"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog"
import { ThemeToggle } from "@/components/ThemeToggle"
import { SidebarTooltip } from "@/components/sidebar/SidebarTooltip"
import { SidebarHeader, SidebarSettingsButton } from "@/components/sidebar/SidebarHeader"
import { SidebarInProgressSection } from "@/components/sidebar/SidebarInProgressSection"
import { SidebarCompletedArchivedSection } from "@/components/sidebar/SidebarCompletedArchivedSection"
import { useRunSessionActions, useRunSessionState } from "@/hooks/useRunSession"
import {
  MOBILE_MENU_BUTTON_ID,
  SIDEBAR_DEFAULT_WIDTH,
  SIDEBAR_MAX_WIDTH,
  SIDEBAR_MIN_WIDTH,
  clampSidebarWidth,
  nextSidebarWidth,
  sidebarShortcutLabel,
} from "@/components/sidebar/sidebarLayout"
export type { LiveRun, PhaseProgress } from "@/components/sidebar/types"

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
  width: number
  onWidthChange: (w: number) => void
  /** When true, renders the sidebar as a modal Sheet drawer instead of a fixed column. */
  isMobile?: boolean
  onOpenSettings?: () => void
}

export function Sidebar({
  collapsed,
  onToggle,
  width,
  onWidthChange,
  isMobile = false,
  onOpenSettings,
}: SidebarProps) {
  const {
    liveRunForSidebar: liveRun,
    selectedRun,
    isViewingLiveRun,
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
  } = useHistory({
    refetchInterval: resolveHistoryRefetchInterval(isRunning, isViewingLiveRun),
  })
  const historyError = historyQueryError ? historyFetchErrorMessage(historyQueryError) : null

  const [completedExpanded, setCompletedExpanded] = useState(false)
  const [archivedExpanded, setArchivedExpanded] = useState(false)
  const [autoExpandedFor, setAutoExpandedFor] = useState<string | null>(null)
  const [wfIdCopied, setWfIdCopied] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const dragStartX = useRef(0)
  const dragStartWidth = useRef(0)

  const {
    prosperoPendingHistory,
    inProgressHistory,
    completedHistory,
    archivedHistory,
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
  })

  if (selectedWorkflowId && selectedWorkflowId !== autoExpandedFor) {
    const inCompleted = completedHistory.some((e) => e.workflow_id === selectedWorkflowId)
    const inArchived = archivedHistory.some((e) => e.workflow_id === selectedWorkflowId)
    if (inCompleted || inArchived) {
      setAutoExpandedFor(selectedWorkflowId)
      if (inCompleted) setCompletedExpanded(true)
      if (inArchived) setArchivedExpanded(true)
    }
  }

  useEffect(() => {
    if (!isDragging) return
    function onMouseMove(e: MouseEvent) {
      onWidthChange(clampSidebarWidth(dragStartWidth.current + e.clientX - dragStartX.current))
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

  function handleResizeKeyDown(e: React.KeyboardEvent) {
    const next = nextSidebarWidth(width, e.key, e.shiftKey)
    if (next == null) return
    e.preventDefault()
    onWidthChange(next)
  }

  const handleCopyWorkflowId = useCallback(async (id: string) => {
    try {
      await navigator.clipboard.writeText(id)
      setWfIdCopied(id)
      setTimeout(() => setWfIdCopied(null), 1500)
    } catch {
      setWfIdCopied(null)
    }
  }, [])

  const railCollapsed = !isMobile && collapsed
  const shortcut = sidebarShortcutLabel()
  const deleteTopic =
    history.find((e) => e.workflow_id === deleteConfirmWorkflowId)?.topic ?? null

  const body = (
    <>
      <div
        className="pointer-events-none absolute inset-0 z-0"
        aria-hidden
        style={{ background: "var(--sidebar-ambient-gradient)" }}
      />

      <SidebarHeader
        collapsed={railCollapsed}
        isMobile={isMobile}
        onGoHome={onGoHome}
        onToggle={onToggle}
      />

      <div className={cn("relative z-10 px-2.5 pt-3 pb-2 shrink-0", railCollapsed && "px-2")}>
        <SidebarTooltip label="New review" collapsed={railCollapsed} side="right">
          <button
            type="button"
            onClick={() => { onNewReview(); if (isMobile) onToggle() }}
            aria-label={railCollapsed ? "New review" : undefined}
            className={cn(
              "sidebar-new-review-button flex items-center gap-2 rounded-lg transition-colors text-sm font-medium w-full",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              railCollapsed ? "justify-center h-9 w-9 mx-auto" : "px-3 py-2",
            )}
          >
            <Plus className="h-4 w-4 shrink-0" aria-hidden />
            {!railCollapsed && "New review"}
          </button>
        </SidebarTooltip>
      </div>

      <nav
        aria-label="Reviews"
        className="flex-1 overflow-y-auto overflow-x-hidden px-2 pb-2 pt-1 relative z-10"
      >
        <SidebarInProgressSection
          collapsed={railCollapsed}
          loadingHistory={loadingHistory}
          historyError={historyError}
          prosperoPendingHistory={prosperoPendingHistory}
          inProgressHistory={inProgressHistory}
          shouldShowStandaloneLiveCard={shouldShowStandaloneLiveCard}
          liveRun={liveRun}
          isLiveRunSelected={isViewingLiveRun}
          isRunning={isRunning}
          isMobile={isMobile}
          selectedWorkflowId={selectedWorkflowId}
          openingId={openingId}
          resumingId={resumingId}
          busyId={busyId}
          wfIdCopied={wfIdCopied}
          notes={notes}
          noteFlashCounters={noteFlashCounters}
          onRefresh={() => void refetchHistory()}
          onToggle={onToggle}
          onSelectLiveRun={onSelectLiveRun}
          onCancel={onCancel}
          onSelect={(row) => void handleOpen(row)}
          onResume={(row) => void handleResume(row)}
          onArchive={(id, topic) => void handleArchive(id, topic)}
          onMoveToCompleted={(id) => void handleMoveToCompleted(id)}
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
        collapsed={railCollapsed}
        selectedWorkflowId={selectedWorkflowId}
        wfIdCopied={wfIdCopied}
        busyId={busyId}
        onToggleCompleted={() => setCompletedExpanded((prev) => !prev)}
        onToggleArchived={() => setArchivedExpanded((prev) => !prev)}
        onOpenLane={(lane) => {
          if (lane === "completed") setCompletedExpanded(true)
          else setArchivedExpanded(true)
          onToggle()
        }}
        onSelect={(row) => void handleOpen(row)}
        onCopyWorkflowId={handleCopyWorkflowId}
        onArchive={(id, topic) => void handleArchive(id, topic)}
        onMoveToCompleted={(id) => void handleMoveToCompleted(id)}
        onMoveToInProgress={(id) => void handleMoveToInProgress(id)}
        onDelete={handleDeleteRequest}
      />

      <div
        className={cn(
          "relative z-10 flex shrink-0 items-center gap-1.5 border-t border-border px-2 py-1.5",
          railCollapsed && "flex-col",
        )}
      >
        {onOpenSettings && (
          <SidebarSettingsButton
            onClick={() => {
              onOpenSettings()
              if (isMobile) onToggle()
            }}
          />
        )}
        <ThemeToggle className="shrink-0" />
        {!isMobile && (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={onToggle}
                aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                aria-keyshortcuts="Meta+B Control+B"
                className={cn(
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-muted transition-colors",
                  "hover:bg-surface-2/60 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  !railCollapsed && "ml-auto",
                )}
              >
                {collapsed ? (
                  <ChevronRight className="h-4 w-4" aria-hidden />
                ) : (
                  <ChevronLeft className="h-4 w-4" aria-hidden />
                )}
              </button>
            </TooltipTrigger>
            <TooltipContent side={railCollapsed ? "right" : "top"} className="text-xs">
              {`${collapsed ? "Expand" : "Collapse"} sidebar (${shortcut})`}
            </TooltipContent>
          </Tooltip>
        )}
      </div>
    </>
  )

  const deleteDialog = (
    <DeleteConfirmDialog
      open={deleteConfirmWorkflowId !== null}
      onOpenChange={(open) => !open && setDeleteConfirmWorkflowId(null)}
      workflowId={deleteConfirmWorkflowId}
      topic={deleteTopic}
      onConfirm={handleDeleteConfirm}
    />
  )

  if (isMobile) {
    return (
      <TooltipProvider delayDuration={0}>
        <Sheet open={!collapsed} onOpenChange={(open) => { if (!open && !collapsed) onToggle() }}>
          <SheetContent
            side="left"
            hideClose
            aria-describedby={undefined}
            onCloseAutoFocus={(e) => {
              e.preventDefault()
              document.getElementById(MOBILE_MENU_BUTTON_ID)?.focus()
            }}
            className="w-72 max-w-[85vw] gap-0 overflow-hidden bg-surface-0 p-0 select-none"
            style={{ paddingTop: "env(safe-area-inset-top)" }}
          >
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            {body}
          </SheetContent>
        </Sheet>
        {deleteDialog}
      </TooltipProvider>
    )
  }

  return (
    <TooltipProvider delayDuration={0}>
      <aside
        aria-label="Sidebar"
        className={cn(
          "fixed left-0 top-0 z-20 h-full bg-surface-0/90 border-r border-border/80 backdrop-blur-sm flex flex-col select-none overflow-hidden",
          !isDragging && "transition-[width] duration-200 ease-in-out",
        )}
        style={{ width: collapsed ? 56 : width, paddingTop: "env(safe-area-inset-top)" }}
      >
        {body}

        {!collapsed && (
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize sidebar"
            aria-valuenow={width}
            aria-valuemin={SIDEBAR_MIN_WIDTH}
            aria-valuemax={SIDEBAR_MAX_WIDTH}
            tabIndex={0}
            title="Drag or use arrow keys to resize. Double-click to reset."
            onMouseDown={handleDragHandleMouseDown}
            onDoubleClick={() => onWidthChange(SIDEBAR_DEFAULT_WIDTH)}
            onKeyDown={handleResizeKeyDown}
            className={cn(
              "absolute top-0 right-0 z-30 h-full w-1.5 cursor-col-resize transition-colors duration-150",
              "hover:bg-intent-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring focus-visible:bg-intent-primary/60",
              isDragging && "bg-intent-primary/60",
            )}
          />
        )}
      </aside>
      {deleteDialog}
    </TooltipProvider>
  )
}
