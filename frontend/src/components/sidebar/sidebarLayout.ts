export const SIDEBAR_DEFAULT_WIDTH = 240
export const SIDEBAR_MIN_WIDTH = 200
export const SIDEBAR_MAX_WIDTH = 420
const RESIZE_STEP = 16

export function clampSidebarWidth(w: number): number {
  return Math.max(SIDEBAR_MIN_WIDTH, Math.min(SIDEBAR_MAX_WIDTH, w))
}

/** Keyboard resizing for the separator. Returns null for keys it does not handle. */
export function nextSidebarWidth(width: number, key: string, shiftKey = false): number | null {
  const step = shiftKey ? RESIZE_STEP * 4 : RESIZE_STEP
  switch (key) {
    case "ArrowLeft":
      return clampSidebarWidth(width - step)
    case "ArrowRight":
      return clampSidebarWidth(width + step)
    case "Home":
      return SIDEBAR_MIN_WIDTH
    case "End":
      return SIDEBAR_MAX_WIDTH
    default:
      return null
  }
}

export function sidebarShortcutLabel(): string {
  const platform = typeof navigator === "undefined" ? "" : navigator.platform
  return /Mac|iPhone|iPad/.test(platform) ? "⌘B" : "Ctrl+B"
}

/** id of the App bar button that opens the mobile drawer; focus returns here on close. */
export const MOBILE_MENU_BUTTON_ID = "sidebar-open-menu"
