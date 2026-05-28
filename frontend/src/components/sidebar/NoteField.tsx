import { useEffect, useRef } from "react"
import { cn } from "@/lib/utils"
import { useNoteAutosave } from "@/hooks/useNoteAutosave"

interface NoteFieldProps {
  workflowId: string
  value: string
  flashKey: number
  onChange: (val: string) => void
}

export function NoteField({
  workflowId,
  value,
  flashKey,
  onChange,
}: NoteFieldProps) {
  const {
    expanded,
    localValue,
    saveState,
    textareaRef,
    handleChange,
    handleFocus,
    handleBlur,
    handleKeyDown,
    expandForEditing,
  } = useNoteAutosave({ workflowId, value, onChange })
  const wrapperRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (flashKey === 0) return
    const el = wrapperRef.current
    if (!el) return
    el.classList.remove("animate-note-flash")
    void el.offsetWidth
    el.classList.add("animate-note-flash")
    const t = setTimeout(() => el.classList.remove("animate-note-flash"), 750)
    return () => clearTimeout(t)
  }, [flashKey])

  return (
    <div
      ref={wrapperRef}
      className="mx-2 my-1 px-2 py-1 rounded"
      onClick={(e) => {
        e.stopPropagation()
        if (!expanded) expandForEditing()
      }}
    >
      <textarea
        ref={textareaRef}
        rows={1}
        value={localValue}
        onChange={handleChange}
        onFocus={handleFocus}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        onClick={(e) => e.stopPropagation()}
        placeholder="Add a note..."
        className={cn(
          "w-full bg-transparent resize-none text-[11px] leading-relaxed",
          "text-intent-warning/90 placeholder-muted",
          "border-none outline-none focus:outline-none",
          "scrollbar-none block",
          !expanded && "cursor-text overflow-hidden",
        )}
        style={
          expanded
            ? { minHeight: "1.4rem", overflowY: "hidden" }
            : { minHeight: "1.4rem", height: "1.4rem", overflowY: "hidden" }
        }
      />
      {saveState !== "idle" && (
        <span className="text-[10px] text-muted tabular-nums">
          {saveState === "saving" ? "Saving..." : "Saved"}
        </span>
      )}
    </div>
  )
}
