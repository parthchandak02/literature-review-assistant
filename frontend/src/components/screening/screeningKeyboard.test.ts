// @vitest-environment jsdom
import { describe, expect, it } from "vitest"
import { ROW_DATA_ATTRIBUTE, isTypingTarget, shortcutFor } from "./screeningKeyboard"

function el(tag: string, attrs: Record<string, string> = {}): HTMLElement {
  const node = document.createElement(tag)
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v)
  return node
}

describe("shortcutFor", () => {
  const row = el("div", { [ROW_DATA_ATTRIBUTE]: "" })

  it("maps the keyboard map", () => {
    expect(shortcutFor({ key: "j", target: row })).toEqual({ type: "move", delta: 1 })
    expect(shortcutFor({ key: "ArrowDown", target: row })).toEqual({ type: "move", delta: 1 })
    expect(shortcutFor({ key: "k", target: row })).toEqual({ type: "move", delta: -1 })
    expect(shortcutFor({ key: "ArrowUp", target: row })).toEqual({ type: "move", delta: -1 })
    expect(shortcutFor({ key: "i", target: row })).toEqual({ type: "decide", decision: "include" })
    expect(shortcutFor({ key: "e", target: row })).toEqual({ type: "decide", decision: "exclude" })
    expect(shortcutFor({ key: "u", target: row })).toEqual({ type: "undo" })
    expect(shortcutFor({ key: "x", target: row })).toEqual({ type: "select" })
    expect(shortcutFor({ key: "?", target: row })).toEqual({ type: "help" })
    expect(shortcutFor({ key: "Enter", target: row })).toEqual({ type: "expand" })
    expect(shortcutFor({ key: " ", target: row })).toEqual({ type: "expand" })
  })

  it("leaves Enter and Space to buttons inside the row", () => {
    expect(shortcutFor({ key: "Enter", target: el("button") })).toBeNull()
    expect(shortcutFor({ key: " ", target: el("button") })).toBeNull()
    expect(shortcutFor({ key: "i", target: el("button") })).toEqual({ type: "decide", decision: "include" })
  })

  it("does not fire while typing or with modifiers", () => {
    expect(shortcutFor({ key: "i", target: el("input", { type: "text" }) })).toBeNull()
    expect(shortcutFor({ key: "j", target: el("input", { type: "search" }) })).toBeNull()
    expect(shortcutFor({ key: "e", target: el("textarea") })).toBeNull()
    expect(shortcutFor({ key: "x", target: el("input", { type: "checkbox" }) })).toEqual({ type: "select" })
    expect(shortcutFor({ key: "j", target: row, metaKey: true })).toBeNull()
    expect(shortcutFor({ key: "i", target: row, ctrlKey: true })).toBeNull()
    expect(shortcutFor({ key: "q", target: row })).toBeNull()
  })

  it("treats contenteditable as typing", () => {
    const div = el("div", { contenteditable: "true" })
    Object.defineProperty(div, "isContentEditable", { value: true })
    expect(isTypingTarget(div)).toBe(true)
  })
})
