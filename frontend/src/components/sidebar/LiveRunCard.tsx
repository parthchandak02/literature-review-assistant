import { Archive, Square } from "lucide-react"
import { cn } from "@/lib/utils"
import { formatRunDate } from "@/lib/format"
import { STATUS_LABEL, STATUS_TEXT } from "@/lib/constants"
import { StatusPulse } from "@/components/run-status"
import { Spinner } from "@/components/ui/feedback"
import { CardProgressBar } from "@/components/sidebar/CardProgressBar"
import { RunCardMetrics } from "@/components/sidebar/RunCardMetrics"
import { SidebarTooltip } from "@/components/sidebar/SidebarTooltip"
import {
  CollapsedWorkflowBadge,
  ExpandedWorkflowBadge,
} from "@/components/sidebar/WorkflowBadges"
import type { LiveRun } from "@/components/sidebar/types"

interface LiveRunCardProps {
  liveRun: LiveRun
  collapsed: boolean
  isLiveRunSelected: boolean
  isRunning: boolean
  isMobile: boolean
  onToggle: () => void
  onSelectLiveRun: () => void
  onCancel?: () => void
  onArchive?: (workflowId: string) => Promise<void>
  archivingId: string | null
  wfIdCopied: string | null
  onCopyWorkflowId: (id: string) => Promise<void>
}

export function LiveRunCard({
  liveRun,
  collapsed,
  isLiveRunSelected,
  isRunning,
  isMobile,
  onToggle,
  onSelectLiveRun,
  onCancel,
  onArchive,
  archivingId,
  wfIdCopied,
  onCopyWorkflowId,
}: LiveRunCardProps) {
  return (
    <SidebarTooltip label={liveRun.topic} collapsed={collapsed} side="right">
      <div className={cn(
        "sidebar-card",
        isLiveRunSelected ? "sidebar-card-selected" : "sidebar-card-hover",
      )}>
        <div className="relative">
          <button
            onClick={() => { onSelectLiveRun(); if (isMobile) onToggle() }}
            className={cn(
              "w-full transition-colors text-left",
              collapsed
                ? "flex justify-center items-center h-9 w-9 mx-auto rounded-xl"
                : "pl-2.5 pr-2 py-2.5",
            )}
          >
            {collapsed ? (
              <CollapsedWorkflowBadge workflowId={liveRun.workflowId} />
            ) : (
              <div className="flex flex-col gap-1 min-w-0">
                <div className="flex items-start gap-2 min-w-0">
                  <ExpandedWorkflowBadge workflowId={liveRun.workflowId} />
                  <span
                    className={cn(
                      "text-xs text-foreground line-clamp-2 leading-snug min-w-0",
                      ((onArchive && liveRun.workflowId && !isRunning) || (isRunning && onCancel)) && "pr-12",
                    )}
                  >
                    {liveRun.topic}
                  </span>
                </div>
                <RunCardMetrics
                  papersFound={liveRun.papersFound}
                  papersIncluded={liveRun.papersIncluded}
                  funnelStages={liveRun.funnelStages}
                  cost={liveRun.cost}
                  workflowId={liveRun.workflowId}
                  copiedWorkflowId={wfIdCopied}
                  onCopyWorkflowId={onCopyWorkflowId}
                />
                <div className="flex items-center justify-between gap-2 min-w-0 text-meta">
                  <div className="flex items-center gap-1.5 shrink-0">
                    <StatusPulse status={liveRun.status} animate={isRunning} size="xs" />
                    <span
                      className={cn(
                        "font-semibold uppercase tracking-wide",
                        STATUS_TEXT[liveRun.status],
                      )}
                    >
                      {STATUS_LABEL[liveRun.status]}
                    </span>
                  </div>
                  <span className="text-muted font-medium tabular-nums shrink-0">
                    {liveRun.startedAt ? formatRunDate(liveRun.startedAt) : "Now"}
                  </span>
                </div>
              </div>
            )}
          </button>
          {!collapsed && isRunning && onCancel && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                onCancel()
              }}
              aria-label="Stop run"
              title="Stop run"
              className="absolute top-0 right-0 flex items-center justify-center h-8 w-8 rounded-bl-md bg-intent-danger hover:bg-intent-danger/85 text-intent-danger-fg transition-colors"
            >
              <Square className="h-2.5 w-2.5 fill-current" />
            </button>
          )}
          {!collapsed && onArchive && liveRun.workflowId && !isRunning && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                void onArchive(liveRun.workflowId!)
              }}
              disabled={archivingId === liveRun.workflowId}
              aria-label="Archive run"
              title="Archive run"
              className={cn(
                "absolute top-0 right-0 flex items-center justify-center h-8 w-8 rounded-bl-md",
                "text-muted hover:text-intent-warning hover:bg-intent-warning-subtle transition-colors",
                archivingId === liveRun.workflowId && "opacity-50 cursor-wait",
              )}
            >
              {archivingId === liveRun.workflowId ? (
                <Spinner size="xs" />
              ) : (
                <Archive className="h-3 w-3" />
              )}
            </button>
          )}
        </div>
        {!collapsed && (
          <CardProgressBar
            status={liveRun.status}
            progress={liveRun.phaseProgress?.value}
          />
        )}
      </div>
    </SidebarTooltip>
  )
}
