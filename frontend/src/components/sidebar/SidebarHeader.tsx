import { BookMarked, Settings } from "lucide-react"
import { cn } from "@/lib/utils"
import { ThemeToggle } from "@/components/ThemeToggle"
import { FRONTEND_BUILD_STAMP, shouldShowFrontendBuildStamp } from "@/lib/buildStamp"
import { ViewToolbar } from "@/components/ui/view-toolbar"

export interface SidebarHeaderProps {
  collapsed: boolean
  isMobile: boolean
  onGoHome?: () => void
  onToggle: () => void
  onOpenSettings?: () => void
}

export function SidebarSettingsButton({ onClick, className }: { onClick: () => void; className?: string }) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      aria-label="Open settings"
      title="Settings"
      className={cn(
        "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-border/80 bg-surface-2/90 text-muted hover:text-foreground hover:bg-surface-3/90 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-intent-primary focus-visible:ring-offset-1",
        className,
      )}
    >
      <Settings className="h-3.5 w-3.5" aria-hidden />
    </button>
  )
}

export function SidebarHeader({ collapsed, isMobile, onGoHome, onToggle, onOpenSettings }: SidebarHeaderProps) {
  return (
    <ViewToolbar
      className="relative z-10 !h-14 shrink-0 gap-2"
      bordered
    >
      <button
        type="button"
        aria-label="LitReview home"
        onClick={() => { onGoHome?.(); if (isMobile) onToggle() }}
        className={cn(
          "flex flex-1 items-center gap-2 min-w-0 text-left",
          "hover:opacity-90 transition-opacity cursor-pointer",
        )}
      >
        <div className="sidebar-brand-chip flex items-center justify-center w-7 h-7 rounded-lg shrink-0">
          <BookMarked className="h-3.5 w-3.5 text-current" />
        </div>
        <span
          className={cn(
            "flex items-baseline gap-1.5 min-w-0 transition-all duration-200",
            collapsed ? "w-0 opacity-0 overflow-hidden" : "w-auto opacity-100",
          )}
        >
          <span className="font-semibold text-sm text-foreground tracking-tight whitespace-nowrap">
            LitReview
          </span>
          {shouldShowFrontendBuildStamp() && (
            <span
              className="text-2xs font-mono text-muted tabular-nums whitespace-nowrap"
              title={`Frontend build ${FRONTEND_BUILD_STAMP}`}
            >
              {FRONTEND_BUILD_STAMP}
            </span>
          )}
        </span>
      </button>
      {!collapsed && onOpenSettings && (
        <SidebarSettingsButton
          onClick={() => {
            onOpenSettings()
            if (isMobile) onToggle()
          }}
        />
      )}
      {!collapsed && <ThemeToggle className="shrink-0" />}
    </ViewToolbar>
  )
}
