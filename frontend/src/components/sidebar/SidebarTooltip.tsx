import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"

interface SidebarTooltipProps {
  label: string
  collapsed: boolean
  side?: "right" | "left" | "top" | "bottom"
  children: React.ReactNode
}

export function SidebarTooltip({
  label,
  collapsed,
  side,
  children,
}: SidebarTooltipProps) {
  if (!collapsed) return <>{children}</>
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent
        side={side ?? "right"}
        className="bg-card border-border text-foreground text-xs max-w-[200px]"
      >
        {label}
      </TooltipContent>
    </Tooltip>
  )
}
