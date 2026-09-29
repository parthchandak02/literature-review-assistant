import { useCallback, useEffect, useState, type CSSProperties, type RefObject } from "react"

const FADE = "2rem"

export interface EdgeFadeState {
  start: boolean
  end: boolean
}

export type EdgeFadeAxis = "x" | "y"

export function edgeFadeMask({ start, end }: EdgeFadeState, axis: EdgeFadeAxis = "x"): CSSProperties | undefined {
  if (!start && !end) return undefined
  const from = start ? `transparent, black ${FADE}` : "black"
  const to = end ? `black calc(100% - ${FADE}), transparent` : "black"
  const mask = `linear-gradient(to ${axis === "x" ? "right" : "bottom"}, ${from}, ${to})`
  return { maskImage: mask, WebkitMaskImage: mask }
}

/** Whether `ref` can scroll further toward its start and end edges. */
export function useEdgeFadeState(ref: RefObject<HTMLElement | null>, axis: EdgeFadeAxis = "x"): EdgeFadeState {
  const [state, setState] = useState<EdgeFadeState>({ start: false, end: false })

  const measure = useCallback(() => {
    const el = ref.current
    if (!el) return
    const pos = axis === "x" ? el.scrollLeft : el.scrollTop
    const max = axis === "x" ? el.scrollWidth - el.clientWidth : el.scrollHeight - el.clientHeight
    const start = pos > 1
    const end = max - pos > 1
    setState((prev) => (prev.start === start && prev.end === end ? prev : { start, end }))
  }, [ref, axis])

  useEffect(() => {
    const el = ref.current
    if (!el) return
    measure()
    // Re-measure after layout and web fonts settle; widths change once the real font loads.
    const frame = requestAnimationFrame(measure)
    let active = true
    void document.fonts?.ready.then(() => {
      if (active) measure()
    })
    el.addEventListener("scroll", measure, { passive: true })
    window.addEventListener("resize", measure)
    const resize = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null
    const observeChildren = () => {
      if (!resize) return
      resize.disconnect()
      resize.observe(el)
      for (const child of Array.from(el.children)) resize.observe(child)
    }
    observeChildren()
    const mutation =
      typeof MutationObserver !== "undefined"
        ? new MutationObserver(() => {
            observeChildren()
            measure()
          })
        : null
    mutation?.observe(el, { childList: true, subtree: true, characterData: true })
    return () => {
      active = false
      cancelAnimationFrame(frame)
      el.removeEventListener("scroll", measure)
      window.removeEventListener("resize", measure)
      resize?.disconnect()
      mutation?.disconnect()
    }
  }, [ref, measure])

  useEffect(measure)

  return state
}

export function useEdgeFade(ref: RefObject<HTMLElement | null>, axis: EdgeFadeAxis = "x"): CSSProperties | undefined {
  return edgeFadeMask(useEdgeFadeState(ref, axis), axis)
}
