import { useEffect, useState } from "react"

export interface HeadingOffset {
  slug: string
  top: number
}

export function pickActiveHeading(headings: HeadingOffset[], activationLine: number): string | null {
  if (headings.length === 0) return null
  let active = headings[0].slug
  for (const h of headings) {
    if (h.top <= activationLine) active = h.slug
    else break
  }
  return active
}

export function activationRootMargin(line: number, viewportHeight: number): string {
  const bottom = Math.max(0, viewportHeight - line - 1)
  return `-${Math.max(0, Math.round(line))}px 0px -${Math.round(bottom)}px 0px`
}

export function useScrollSpy(
  slugs: string[],
  container: HTMLElement | null,
  getActivationLine: () => number,
): string | null {
  const [active, setActive] = useState<string | null>(null)
  const key = slugs.join("|")

  useEffect(() => {
    if (!container || slugs.length === 0 || typeof IntersectionObserver === "undefined") return
    const elements = slugs
      .map((slug) => container.querySelector<HTMLElement>(`#${CSS.escape(slug)}`))
      .filter((el): el is HTMLElement => el != null)
    if (elements.length === 0) return

    const line = getActivationLine()
    const update = () => {
      const offsets = elements.map((el) => ({ slug: el.id, top: el.getBoundingClientRect().top }))
      setActive(pickActiveHeading(offsets, line + 1))
    }
    const observer = new IntersectionObserver(update, {
      rootMargin: activationRootMargin(line, window.innerHeight),
      threshold: [0, 1],
    })
    elements.forEach((el) => observer.observe(el))
    update()
    return () => observer.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- key tracks slugs by value
  }, [key, container, getActivationLine])

  return active
}
