import type { MouseEvent, PointerEvent } from "react"

// Shared by every card: the tap that dismisses one card's menu lands on a sibling card
// as a click once the menu is gone, so card clicks are ignored while a menu is open
// and briefly after an outside press closed it.
const MENU_DISMISS_GUARD_MS = 400
const openMenus = new Set<() => void>()
let lastOutsideDismissAt = -Infinity

/** Registers an open card menu by its close callback; returns the unregister function. */
export function trackCardMenu(close: () => void): () => void {
  openMenus.add(close)
  return () => {
    openMenus.delete(close)
  }
}

export function markOutsideDismiss() {
  lastOutsideDismissAt = performance.now()
}

/** Closes every open card menu. Returns whether any was open. */
export function dismissOpenCardMenus(): boolean {
  if (openMenus.size === 0) return false
  for (const close of [...openMenus]) close()
  return true
}

/**
 * Touch adjustment retargets a tap that lands just outside the menu onto the menu panel,
 * which Radix then treats as an inside press. The coordinates still report the real touch point.
 */
export function isPressOutsideOwnBox(e: PointerEvent<HTMLElement>): boolean {
  if (e.target !== e.currentTarget) return false
  const box = e.currentTarget.getBoundingClientRect()
  return e.clientX < box.left || e.clientX > box.right || e.clientY < box.top || e.clientY > box.bottom
}

export function swallowMenuDismissClick(e: MouseEvent<HTMLElement>) {
  // Clicks from portaled menu items and dialogs bubble here through the React tree.
  if (!e.currentTarget.contains(e.target as Node)) return
  if (openMenus.size === 0 && performance.now() - lastOutsideDismissAt > MENU_DISMISS_GUARD_MS) return
  e.preventDefault()
  e.stopPropagation()
}
