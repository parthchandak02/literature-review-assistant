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
        "relative z-20 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500/50 focus-visible:ring-offset-1",
        isLight
          ? "border-zinc-300/90 bg-zinc-200/80 text-amber-500 hover:bg-zinc-100"
          : "border-zinc-600/80 bg-zinc-800/90",
        !isLight && "text-violet-200 hover:bg-zinc-700/90",
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
