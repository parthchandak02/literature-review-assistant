import { BookMarked } from "lucide-react"
import { cn } from "@/lib/utils"
import { ThemeToggle } from "@/components/ThemeToggle"
import { FRONTEND_BUILD_STAMP, shouldShowFrontendBuildStamp } from "@/lib/buildStamp"
import { ViewToolbar } from "@/components/ui/view-toolbar"

export interface SidebarHeaderProps {
  collapsed: boolean
  isMobile: boolean
  onGoHome?: () => void
  onToggle: () => void
}

export function SidebarHeader({ collapsed, isMobile, onGoHome, onToggle }: SidebarHeaderProps) {
  return (
    <ViewToolbar
      className="relative z-10 !h-14 shrink-0 gap-2"
      bordered
    >
      <button
        type="button"
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
              className="text-[10px] font-mono text-muted tabular-nums whitespace-nowrap"
              title={`Frontend build ${FRONTEND_BUILD_STAMP}`}
            >
              {FRONTEND_BUILD_STAMP}
            </span>
          )}
        </span>
      </button>
      {!collapsed && <ThemeToggle className="shrink-0" />}
    </ViewToolbar>
  )
}
