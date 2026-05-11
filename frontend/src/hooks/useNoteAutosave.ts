import { useEffect, useRef, useState } from "react"
import { saveNote } from "@/lib/api"

type SaveState = "idle" | "saving" | "saved"

interface UseNoteAutosaveArgs {
  workflowId: string
  value: string
  onChange: (val: string) => void
}

export function useNoteAutosave({ workflowId, value, onChange }: UseNoteAutosaveArgs) {
  const [localValue, setLocalValue] = useState(value)
  const [saveState, setSaveState] = useState<SaveState>("idle")
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const savedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  function recalcHeight() {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 144)}px`
  }

  useEffect(() => {
    if (document.activeElement !== textareaRef.current) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLocalValue(value)
    }
  }, [value])

  useEffect(() => {
    recalcHeight()
  }, [localValue])

  async function persistNote(val: string) {
    try {
      await saveNote(workflowId, val)
      setSaveState("saved")
      if (savedTimerRef.current) clearTimeout(savedTimerRef.current)
      savedTimerRef.current = setTimeout(() => setSaveState("idle"), 1500)
    } catch {
      setSaveState("idle")
    }
  }

  function scheduleSave(val: string) {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    setSaveState("saving")
    debounceRef.current = setTimeout(() => {
      void persistNote(val)
    }, 500)
  }

  function handleChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const val = e.target.value
    setLocalValue(val)
    onChange(val)
    scheduleSave(val)
  }

  function handleBlur() {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current)
      debounceRef.current = null
      void persistNote(localValue)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    e.stopPropagation()
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
        debounceRef.current = null
      }
      void persistNote(localValue)
      textareaRef.current?.blur()
    }
    if (e.key === "Escape") {
      e.preventDefault()
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
        debounceRef.current = null
      }
      textareaRef.current?.blur()
    }
  }

  return {
    localValue,
    saveState,
    textareaRef,
    handleChange,
    handleBlur,
    handleKeyDown,
  }
}
