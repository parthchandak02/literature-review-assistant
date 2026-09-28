export interface FollowState {
  following: boolean
  /** Row count when follow was paused; rows past this index are "new". */
  anchor: number
}

export interface ScrollSample {
  atEnd: boolean
  scrolledBackward: boolean
  count: number
}

export function nextFollowState(prev: FollowState, sample: ScrollSample): FollowState {
  if (sample.atEnd) {
    return prev.following && prev.anchor === sample.count ? prev : { following: true, anchor: sample.count }
  }
  if (prev.following && sample.scrolledBackward) {
    return { following: false, anchor: sample.count }
  }
  return prev
}

export function resumeFollow(count: number): FollowState {
  return { following: true, anchor: count }
}

export function pauseFollow(count: number): FollowState {
  return { following: false, anchor: count }
}

/** Number of event rows appended after the anchor while follow was paused. */
export function countNewEvents(items: ReadonlyArray<{ kind: string }>, state: FollowState): number {
  if (state.following || state.anchor >= items.length) return 0
  let n = 0
  for (let i = state.anchor; i < items.length; i++) {
    if (items[i].kind === "event") n++
  }
  return n
}

export function newEventsLabel(n: number): string {
  return `${n} new event${n === 1 ? "" : "s"}`
}

export interface AnnounceSource {
  kind: "phase-sep" | "event"
  label?: string
  isError?: boolean
  message?: string
}

/** Screen-reader text for newly appended rows: phase transitions and errors only. */
export function announcementFor(items: ReadonlyArray<AnnounceSource>): string | null {
  let phase: string | null = null
  let errors = 0
  let lastError = ""
  for (const item of items) {
    if (item.kind === "phase-sep" && item.label) phase = item.label
    else if (item.kind === "event" && item.isError) {
      errors++
      lastError = item.message ?? ""
    }
  }
  const parts: string[] = []
  if (phase) parts.push(`Now in ${phase}.`)
  if (errors === 1) parts.push(`Error: ${lastError}`)
  else if (errors > 1) parts.push(`${errors} new errors. Latest: ${lastError}`)
  return parts.length ? parts.join(" ") : null
}
