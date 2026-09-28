import { describe, expect, it } from "vitest"
import {
  SIDEBAR_MAX_WIDTH,
  SIDEBAR_MIN_WIDTH,
  clampSidebarWidth,
  nextSidebarWidth,
} from "./sidebarLayout"

describe("nextSidebarWidth", () => {
  it("steps 16px with arrows and 64px with Shift", () => {
    expect(nextSidebarWidth(240, "ArrowRight")).toBe(256)
    expect(nextSidebarWidth(240, "ArrowLeft")).toBe(224)
    expect(nextSidebarWidth(240, "ArrowRight", true)).toBe(304)
  })

  it("clamps to the min and max and supports Home/End", () => {
    expect(nextSidebarWidth(SIDEBAR_MIN_WIDTH, "ArrowLeft")).toBe(SIDEBAR_MIN_WIDTH)
    expect(nextSidebarWidth(SIDEBAR_MAX_WIDTH, "ArrowRight")).toBe(SIDEBAR_MAX_WIDTH)
    expect(nextSidebarWidth(300, "Home")).toBe(SIDEBAR_MIN_WIDTH)
    expect(nextSidebarWidth(300, "End")).toBe(SIDEBAR_MAX_WIDTH)
    expect(clampSidebarWidth(9999)).toBe(SIDEBAR_MAX_WIDTH)
  })

  it("ignores other keys", () => {
    expect(nextSidebarWidth(240, "Enter")).toBeNull()
    expect(nextSidebarWidth(240, "ArrowUp")).toBeNull()
  })
})
