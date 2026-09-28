// @vitest-environment jsdom
import "@/test/dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import { act, renderHook } from "@testing-library/react"
import { activationRootMargin, pickActiveHeading, useScrollSpy } from "./tocScrollSpy"

describe("pickActiveHeading", () => {
  const headings = [
    { slug: "intro", top: -400 },
    { slug: "methods", top: 50 },
    { slug: "results", top: 600 },
  ]

  it("picks the last heading above the activation line", () => {
    expect(pickActiveHeading(headings, 100)).toBe("methods")
    expect(pickActiveHeading(headings, 10)).toBe("intro")
    expect(pickActiveHeading(headings, 700)).toBe("results")
  })

  it("falls back to the first heading before any has scrolled past", () => {
    expect(pickActiveHeading([{ slug: "a", top: 300 }, { slug: "b", top: 500 }], 100)).toBe("a")
  })

  it("handles no headings", () => {
    expect(pickActiveHeading([], 100)).toBeNull()
  })
})

describe("activationRootMargin", () => {
  it("builds a 1px band at the activation line", () => {
    expect(activationRootMargin(120, 800)).toBe("-120px 0px -679px 0px")
    expect(activationRootMargin(-5, 10)).toBe("-0px 0px -14px 0px")
  })
})

describe("useScrollSpy", () => {
  const original = globalThis.IntersectionObserver
  afterEach(() => {
    globalThis.IntersectionObserver = original
  })

  it("updates the active slug when the observer fires", () => {
    let fire: () => void = () => {}
    const observe = vi.fn()
    globalThis.IntersectionObserver = class {
      constructor(cb: () => void) {
        fire = cb
      }
      observe = observe
      disconnect = vi.fn()
      unobserve = vi.fn()
      takeRecords = () => []
      root = null
      rootMargin = ""
      thresholds = []
    } as unknown as typeof IntersectionObserver

    const container = document.createElement("div")
    const tops: Record<string, number> = { a: 0, b: 400 }
    for (const id of ["a", "b"]) {
      const h = document.createElement("h2")
      h.id = id
      h.getBoundingClientRect = () => ({ top: tops[id] }) as DOMRect
      container.appendChild(h)
    }
    const line = () => 100
    const { result } = renderHook(() => useScrollSpy(["a", "b"], container, line))
    expect(observe).toHaveBeenCalledTimes(2)
    expect(result.current).toBe("a")

    tops.a = -500
    tops.b = 80
    act(() => fire())
    expect(result.current).toBe("b")
  })
})
