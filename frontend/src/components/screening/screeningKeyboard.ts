import type { HumanDecision } from "./screeningModel"

export type ShortcutCommand =
  | { type: "move"; delta: 1 | -1 }
  | { type: "decide"; decision: HumanDecision }
  | { type: "undo" }
  | { type: "expand" }
  | { type: "select" }
  | { type: "help" }

export interface ShortcutEventLike {
  key: string
  target: EventTarget | null
  metaKey?: boolean
  ctrlKey?: boolean
  altKey?: boolean
}

export const ROW_DATA_ATTRIBUTE = "data-screening-row"

export const SCREENING_SHORTCUTS: ReadonlyArray<{ keys: string[]; label: string }> = [
  { keys: ["j", "↓"], label: "Next paper" },
  { keys: ["k", "↑"], label: "Previous paper" },
  { keys: ["i"], label: "Include" },
  { keys: ["e"], label: "Exclude" },
  { keys: ["u"], label: "Undo last change" },
  { keys: ["Enter", "Space"], label: "Expand or collapse" },
  { keys: ["x"], label: "Select or deselect" },
  { keys: ["?"], label: "Show shortcuts" },
]

function isElement(target: EventTarget | null): target is Element {
  return typeof Element !== "undefined" && target instanceof Element
}

export function isTypingTarget(target: EventTarget | null): boolean {
  if (!isElement(target)) return false
  if (target instanceof HTMLElement && target.isContentEditable) return true
  const tag = target.tagName
  if (tag === "TEXTAREA" || tag === "SELECT") return true
  if (tag !== "INPUT") return false
  const type = (target as HTMLInputElement).type
  return type !== "checkbox" && type !== "radio" && type !== "button"
}

function isRowTarget(target: EventTarget | null): boolean {
  return isElement(target) && target.hasAttribute(ROW_DATA_ATTRIBUTE)
}

export function shortcutFor(event: ShortcutEventLike): ShortcutCommand | null {
  if (event.metaKey || event.ctrlKey || event.altKey) return null
  if (isTypingTarget(event.target)) return null
  switch (event.key) {
    case "j":
    case "ArrowDown":
      return { type: "move", delta: 1 }
    case "k":
    case "ArrowUp":
      return { type: "move", delta: -1 }
    case "i":
      return { type: "decide", decision: "include" }
    case "e":
      return { type: "decide", decision: "exclude" }
    case "u":
      return { type: "undo" }
    case "x":
      return { type: "select" }
    case "?":
      return { type: "help" }
    case "Enter":
    case " ":
      // Buttons and checkboxes inside a row keep their native Enter/Space.
      return isRowTarget(event.target) ? { type: "expand" } : null
    default:
      return null
  }
}
