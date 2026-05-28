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
  const [expanded, setExpanded] = useState(() => value.trim().length > 0)
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
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setExpanded(value.trim().length > 0)
    }
  }, [value])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    if (!expanded) {
      el.style.height = "1.4rem"
      el.style.overflowY = "hidden"
      return
    }
    recalcHeight()
  }, [localValue, expanded])

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
    if (!localValue.trim()) setExpanded(false)
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

  function handleFocus() {
    setExpanded(true)
  }

  function expandForEditing() {
    setExpanded(true)
    requestAnimationFrame(() => {
      textareaRef.current?.focus()
      recalcHeight()
    })
  }

  return {
    expanded,
    localValue,
    saveState,
    textareaRef,
    handleChange,
    handleFocus,
    handleBlur,
    handleKeyDown,
    expandForEditing,
  }
}
