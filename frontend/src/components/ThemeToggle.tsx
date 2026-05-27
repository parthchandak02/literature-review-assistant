import { Moon, Sun } from "lucide-react"
import { cn } from "@/lib/utils"
import { useThemeStore } from "@/lib/themeStore"

interface ThemeToggleProps {
  className?: string
}

export function ThemeToggle({ className }: ThemeToggleProps) {
  const { theme, toggleTheme } = useThemeStore()
  const isLight = theme === "light"

  return (
    <button
      type="button"
      aria-label={isLight ? "Switch to dark mode" : "Switch to light mode"}
      onClick={(e) => {
        e.stopPropagation()
        toggleTheme()
      }}
      className={cn(
        "relative z-20 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-intent-primary focus-visible:ring-offset-1",
        isLight
          ? "border-border/90 bg-surface-2/80 text-intent-warning hover:bg-surface-1"
          : "border-border/80 bg-surface-2/90",
        !isLight && "text-intent-active hover:bg-surface-3/90",
        className,
      )}
    >
      {isLight ? (
        <Sun className="h-3.5 w-3.5" aria-hidden />
      ) : (
        <Moon className="h-3.5 w-3.5" aria-hidden />
      )}
    </button>
  )
}
