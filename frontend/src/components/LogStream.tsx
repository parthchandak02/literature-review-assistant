import { forwardRef, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState } from "react"
import { useVirtualizer } from "@tanstack/react-virtual"
import { ArrowDown, ChevronDown } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { humanizeLogTag } from "@/lib/humanize"
import {
  announcementFor,
  countNewEvents,
  newEventsLabel,
  nextFollowState,
  pauseFollow,
  resumeFollow,
  type AnnounceSource,
  type FollowState,
} from "@/lib/logFollow"
import { milestoneForPhase, PHASE_MILESTONES, type PhaseMilestone } from "@/lib/constants"
import type { ReviewEvent } from "@/lib/api"
import { eventToLogEntry, fmtTs } from "@/lib/logLine"
import type { LogLevel } from "@/lib/logLine"
import type { LogRenderEntry } from "@/lib/logLine"

// Event types that produce no meaningful user-facing log line and should be
// filtered out of the rendered output (infrastructure / plumbing events).
// "progress" is shown as compact dim ticks so calibration steps are visible.
const SKIP_EVENT_TYPES = new Set(["workflow_id_ready", "heartbeat"])

// ---------------------------------------------------------------------------
// Render item types (phase separators + event rows)
// ---------------------------------------------------------------------------

type RenderItem =
  | { kind: "phase-sep"; phase: string; label: string; description?: string; ts?: string; key: string }
  | { kind: "event"; ev: ReviewEvent; key: string }

function stableStringify(value: unknown): string {
  if (value == null) return String(value)
  if (typeof value !== "object") return JSON.stringify(value)
  if (Array.isArray(value)) return `[${value.map((v) => stableStringify(v)).join(",")}]`
  const entries = Object.entries(value as Record<string, unknown>)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${JSON.stringify(k)}:${stableStringify(v)}`)
  return `{${entries.join(",")}}`
}

function eventStableKey(ev: ReviewEvent): string {
  if (ev.id) return `event-${ev.id}`
  const ts = "ts" in ev ? (ev as { ts?: string }).ts ?? "" : ""
  const base = `event-${ev.type}-${ts}`
  switch (ev.type) {
    case "phase_start":
    case "phase_done":
      return `${base}-${ev.phase}`
    case "progress":
      return `${base}-${ev.phase}-${ev.current}-${ev.total}`
    case "screening_decision":
      return `${base}-${ev.paper_id}-${ev.stage}-${ev.decision}`
    case "connector_result":
      return `${base}-${ev.name}-${ev.status}-${ev.records}`
    case "api_call":
      return `${base}-${ev.phase}-${ev.call_type}-${ev.paper_id ?? ""}-${ev.section_name ?? ""}-${ev.status}`
    case "status":
      return `${base}-${ev.message}`
    default:
      return `${base}-${stableStringify(ev)}`
  }
}

const START_MILESTONE = PHASE_MILESTONES.find((milestone) => milestone.key === "start")!

function milestoneByKey(key: string): PhaseMilestone | null {
  return PHASE_MILESTONES.find((milestone) => milestone.key === key) ?? null
}

function inferMilestoneFromEventType(ev: ReviewEvent): PhaseMilestone | null {
  switch (ev.type) {
    case "connector_result":
    case "screening_decision":
    case "screening_prefilter_done":
    case "deterministic_exclusion_qa_sample":
    case "batch_screen_done":
    case "screening_cap_overflow":
    case "screening_calibration":
    case "pdf_result":
    case "search_override_status":
      return milestoneForPhase("phase_2_search")
    case "extraction_paper":
      return milestoneForPhase("phase_4_extraction_quality")
    case "synthesis":
      return milestoneForPhase("phase_5_synthesis")
    default:
      return null
  }
}

function resolveEventMilestone(
  ev: ReviewEvent,
  hasSeenPhasedEvent: boolean,
  currentMilestoneKey: string | null,
): PhaseMilestone | null {
  const phase = "phase" in ev ? ev.phase : undefined
  if (phase) {
    const milestone = milestoneForPhase(phase)
    if (milestone) return milestone
  }
  if (!hasSeenPhasedEvent) return null
  const inferred = inferMilestoneFromEventType(ev)
  if (inferred) return inferred
  if (currentMilestoneKey) return milestoneByKey(currentMilestoneKey)
  return null
}

function nextEventTs(events: ReviewEvent[], from: number): string | undefined {
  for (let j = from + 1; j < events.length; j++) {
    const ts = "ts" in events[j] ? (events[j] as { ts?: string }).ts : undefined
    if (ts) return ts
  }
  return undefined
}

// eslint-disable-next-line react-refresh/only-export-components -- pure helper tested alongside LogStream
export function buildRenderItems(events: ReviewEvent[]): RenderItem[] {
  const items: RenderItem[] = []
  const keyCounts = new Map<string, number>()
  let currentMilestoneKey: string | null = null
  let hasSeenPhasedEvent = false

  for (let i = 0; i < events.length; i++) {
    const ev = events[i]
    const ts = "ts" in ev ? (ev as { ts?: string }).ts ?? "" : ""

    if (SKIP_EVENT_TYPES.has(ev.type)) continue

    const rawKey = eventStableKey(ev)
    const duplicateIndex = keyCounts.get(rawKey) ?? 0
    keyCounts.set(rawKey, duplicateIndex + 1)
    const evKey = duplicateIndex === 0 ? rawKey : `${rawKey}-dup-${duplicateIndex}`

    const milestone: PhaseMilestone =
      resolveEventMilestone(ev, hasSeenPhasedEvent, currentMilestoneKey) ??
      (currentMilestoneKey ? milestoneByKey(currentMilestoneKey) : START_MILESTONE) ??
      START_MILESTONE

    if (milestone.key !== "start") {
      hasSeenPhasedEvent = true
    }

    if (milestone.key !== currentMilestoneKey) {
      const descRaw = ev.type === "phase_start" ? ev.description : undefined
      const desc =
        typeof descRaw === "string" && descRaw.trim().length > 0 ? descRaw.trim() : undefined
      items.push({
        kind: "phase-sep",
        phase: milestone.key,
        label: milestone.label,
        description: desc,
        ts: desc ? ts || nextEventTs(events, i) : undefined,
        key: `sep-${milestone.key}-${evKey}-${ts}`,
      })
      currentMilestoneKey = milestone.key
    }

    // phase_start is represented by a separator only to avoid duplicate rows.
    if (ev.type === "phase_start") continue

    items.push({
      kind: "event",
      ev,
      key: evKey,
    })
  }

  return items
}

// ---------------------------------------------------------------------------
// Row styling per level
// ---------------------------------------------------------------------------

function levelClass(level: LogLevel): string {
  switch (level) {
    case "error":
      return "text-intent-danger"
    case "warn":
      return "text-intent-warning"
    case "info":
      return "text-foreground"
    default:
      return "text-muted"
  }
}

function decisionStyle(level: LogLevel): { rowClass: string; tagClass: string; textClass: string } {
  if (level === "include") {
    return {
      rowClass: "border-intent-success bg-intent-success-subtle",
      tagClass: "text-intent-success font-semibold",
      textClass: "text-intent-success",
    }
  }
  if (level === "exclude-heuristic") {
    return {
      rowClass: "border-intent-warning-border bg-intent-warning-subtle",
      tagClass: "text-intent-warning font-semibold",
      textClass: "text-intent-warning",
    }
  }
  return {
    rowClass: "border-border bg-surface-2/20",
    tagClass: "text-muted font-semibold",
    textClass: "text-foreground",
  }
}

const EXPAND_THRESHOLD = 240
const END_THRESHOLD_PX = 24
const LOG_HEADER_PX = 32
const ROW_GRID =
  "grid grid-cols-1 gap-x-2 @md:grid-cols-[4.75rem_6.5rem_minmax(0,1fr)] items-start"
const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"

/** The tag column truncates, so the tooltip always carries the full label. */
function tagTitle({ label, description }: { label: string; description?: string }): string {
  return description ? `${label}: ${description}` : label
}

function isDecision(level: LogLevel): boolean {
  return level === "include" || level === "exclude" || level === "exclude-heuristic"
}

function LogRow({
  entry,
  traceback,
  expanded,
  onToggle,
}: {
  entry: LogRenderEntry
  traceback?: string
  expanded: boolean
  onToggle: () => void
}) {
  const tagInfo = humanizeLogTag(entry.tag)
  const decision = isDecision(entry.level)
  const style = decision ? decisionStyle(entry.level) : null
  const long = entry.message.length > EXPAND_THRESHOLD
  const canExpand = long || !!entry.detail
  const message = long && !expanded ? `${entry.message.slice(0, EXPAND_THRESHOLD).trimEnd()}…` : entry.message
  const subTag = entry.subTag === "AUTO" ? humanizeLogTag("AUTO") : null

  return (
    <div className={cn("py-px", decision && ["-ml-2.5 pl-2 border-l-2 rounded-r", style?.rowClass])}>
      <div className={cn(ROW_GRID, decision ? style?.textClass : levelClass(entry.level))}>
        <div className="flex items-baseline gap-2 min-w-0 @md:contents">
          <span className="num text-muted">{entry.ts ? `[${entry.ts}]` : ""}</span>
          <span
            className={cn("min-w-0 truncate", decision ? style?.tagClass : "text-muted")}
            title={tagTitle(tagInfo)}
          >
            {tagInfo.label}
          </span>
        </div>
        <div className="min-w-0 whitespace-pre-wrap [overflow-wrap:anywhere]">
          {subTag && (
            <span
              className="mr-1.5 rounded border border-current/30 px-1 font-sans text-xs font-medium"
              title={subTag.description}
            >
              {subTag.label}
            </span>
          )}
          <span title={!expanded && entry.detail ? entry.detail : undefined}>{message}</span>
          {canExpand && (
            <>
              {" "}
              <button
                type="button"
                onClick={onToggle}
                aria-expanded={expanded}
                aria-label={expanded ? "Show less" : "Show more"}
                title={expanded ? "Show less" : "Show more"}
                className={cn(
                  "touch-hit inline-flex align-middle items-center justify-center rounded text-muted/70 hover:text-foreground transition-colors motion-reduce:transition-none pointer-coarse:min-h-6 pointer-coarse:min-w-6",
                  FOCUS_RING,
                )}
              >
                <ChevronDown aria-hidden className={cn("h-3.5 w-3.5 transition-transform motion-reduce:transition-none", expanded && "rotate-180")} />
              </button>
            </>
          )}
          {expanded && entry.detail && <div className="mt-0.5 text-muted">{entry.detail}</div>}
        </div>
      </div>
      {traceback && (
        <pre className="text-xs text-muted whitespace-pre-wrap [overflow-wrap:anywhere] font-mono pl-4 border-l-2 border-intent-danger-border mt-1">
          {traceback}
        </pre>
      )}
    </div>
  )
}

const PHASE_LABEL_CLASS = "font-semibold tracking-widest uppercase text-intent-primary"

const PHASE_TAG = humanizeLogTag("PHASE")

function PhaseSeparator({ label, description, ts }: { label: string; description?: string; ts?: string }) {
  const time = fmtTs(ts)
  return (
    <div className="pt-3">
      <div className="flex items-center gap-2 pb-1">
        <span className={cn(PHASE_LABEL_CLASS, "shrink-0")}>{label}</span>
        <div className="h-px flex-1 bg-border" aria-hidden />
      </div>
      {description ? (
        <div className={cn(ROW_GRID, "py-px text-muted")}>
          <div className="flex items-baseline gap-2 min-w-0 @md:contents">
            <span className="num">{time ? `[${time}]` : ""}</span>
            <span className="min-w-0 truncate" title={tagTitle(PHASE_TAG)}>
              {PHASE_TAG.label}
            </span>
          </div>
          <span className="min-w-0 [overflow-wrap:anywhere]">{description}</span>
        </div>
      ) : null}
    </div>
  )
}

// ---------------------------------------------------------------------------
// LogStream
// ---------------------------------------------------------------------------

export interface LogStreamHandle {
  scrollToPhase: (phase: string) => void
}

interface LogStreamProps {
  events: ReviewEvent[]
  /** When false, suppresses auto-scroll to bottom (use when a filter is active). */
  autoScroll?: boolean
}

function toAnnounceSource(item: RenderItem): AnnounceSource {
  if (item.kind === "phase-sep") return { kind: "phase-sep", label: item.label }
  if (item.ev.type !== "error" && item.ev.type !== "api_call") return { kind: "event" }
  const entry = eventToLogEntry(item.ev)
  return { kind: "event", isError: entry.severity === "error", message: entry.message }
}

export const LogStream = forwardRef<LogStreamHandle, LogStreamProps>(function LogStream(
  { events, autoScroll = true },
  ref,
) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const lastOffsetRef = useRef(0)
  const renderItems = useMemo(() => buildRenderItems(events), [events])
  const [expandedRows, setExpandedRows] = useState<Set<string>>(() => new Set())
  const [follow, setFollow] = useState<FollowState>(() => resumeFollow(renderItems.length))
  const [announcement, setAnnouncement] = useState("")
  const [prevItems, setPrevItems] = useState(renderItems)
  const [prevAutoScroll, setPrevAutoScroll] = useState(autoScroll)

  if (prevItems !== renderItems) {
    setPrevItems(renderItems)
    const prevLen = prevItems.length
    const appended =
      prevLen > 0 &&
      renderItems.length > prevLen &&
      renderItems[prevLen - 1]?.key === prevItems[prevLen - 1]?.key
    if (appended) {
      const text = announcementFor(renderItems.slice(prevLen).map(toAnnounceSource))
      if (text) setAnnouncement(text)
    }
  }

  if (prevAutoScroll !== autoScroll) {
    setPrevAutoScroll(autoScroll)
    if (autoScroll) setFollow(resumeFollow(renderItems.length))
  }

  const followActive = autoScroll && follow.following

  const phaseSepIndex = useMemo(() => {
    const out = new Array<number>(renderItems.length)
    let current = -1
    renderItems.forEach((item, i) => {
      if (item.kind === "phase-sep") current = i
      out[i] = current
    })
    return out
  }, [renderItems])

  // eslint-disable-next-line react-hooks/incompatible-library -- no React Compiler in this app; virtualizer re-renders via onChange
  const virtualizer = useVirtualizer({
    count: renderItems.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: (i) => (renderItems[i]?.kind === "phase-sep" ? 36 : 22),
    getItemKey: (i) => renderItems[i]?.key ?? i,
    overscan: 12,
    paddingStart: 4,
    scrollPaddingStart: LOG_HEADER_PX,
    paddingEnd: 16,
    anchorTo: "end",
    followOnAppend: followActive,
    scrollEndThreshold: END_THRESHOLD_PX,
    initialRect: { width: 800, height: 480 },
    onChange: (instance) => {
      const offset = instance.scrollOffset ?? 0
      const scrolledBackward = offset < lastOffsetRef.current - 1
      lastOffsetRef.current = offset
      const atEnd = instance.isAtEnd(END_THRESHOLD_PX)
      const count = instance.options.count
      setFollow((prev) => nextFollowState(prev, { atEnd, scrolledBackward, count }))
    },
  })

  useLayoutEffect(() => {
    if (!autoScroll) return
    const count = virtualizer.options.count
    if (count > 0) virtualizer.scrollToIndex(count - 1, { align: "end" })
  }, [autoScroll, virtualizer])

  const jumpToLatest = () => {
    const count = renderItems.length
    setFollow(resumeFollow(count))
    if (count > 0) virtualizer.scrollToIndex(count - 1, { align: "end" })
  }

  useImperativeHandle(ref, () => ({
    scrollToPhase: (phase: string) => {
      const idx = renderItems.findIndex((item) => item.kind === "phase-sep" && item.phase === phase)
      if (idx < 0) return
      setFollow(pauseFollow(renderItems.length))
      virtualizer.scrollToIndex(idx, { align: "start" })
    },
  }))

  const toggleExpanded = (rowKey: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(rowKey)) next.delete(rowKey)
      else next.add(rowKey)
      return next
    })
  }

  if (events.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-sm text-muted bg-card border border-border rounded-panel">
        Events will appear here once the review starts.
      </div>
    )
  }

  const virtualItems = virtualizer.getVirtualItems()
  const offset = virtualizer.scrollOffset ?? 0
  const firstVisible = virtualItems.find((v) => v.end > offset) ?? virtualItems[0]
  const headerIndex = firstVisible ? phaseSepIndex[firstVisible.index] : -1
  const headerItem = headerIndex >= 0 ? renderItems[headerIndex] : null
  const headerVirtual = virtualItems.find((v) => v.index === headerIndex)
  const headerLabel =
    headerItem?.kind === "phase-sep" && (!headerVirtual || headerVirtual.start + 12 < offset)
      ? headerItem.label
      : null
  const newCount = countNewEvents(renderItems, follow)
  const showPill = autoScroll && !follow.following

  return (
    <div className="relative [--log-header-h:2rem] [--log-h:clamp(22rem,calc(100dvh-20rem),40rem)] [--log-pill-bar-h:2.75rem]">
      {headerLabel && (
        <div
          data-testid="log-current-phase"
          className="pointer-events-none absolute inset-x-px top-px z-10 rounded-t-panel"
        >
          <div className="flex h-(--log-header-h) items-center gap-2 rounded-t-panel bg-background px-4 font-mono text-xs leading-5">
            <span className="sr-only">Current phase: </span>
            <span className={cn(PHASE_LABEL_CLASS, "shrink-0")}>{headerLabel}</span>
            <div className="h-px flex-1 bg-border" aria-hidden />
          </div>
          <div
            data-testid="log-current-phase-fade"
            className="h-6 bg-linear-to-b from-background from-35% via-background/70 to-transparent"
            aria-hidden
          />
        </div>
      )}

      <div
        ref={scrollRef}
        className={cn(
          "@container w-full rounded-panel border border-border bg-background overflow-y-auto",
          showPill ? "h-[calc(var(--log-h)-var(--log-pill-bar-h))]" : "h-(--log-h)",
          FOCUS_RING,
        )}
        role="log"
        aria-live="off"
        aria-label="Event log"
        tabIndex={0}
      >
        <div className="relative w-full" style={{ height: virtualizer.getTotalSize() }}>
          <div
            className="absolute left-0 top-0 w-full px-4 font-mono text-xs leading-5"
            style={{ transform: `translateY(${virtualItems[0]?.start ?? 0}px)` }}
          >
            {virtualItems.map((v) => {
              const item = renderItems[v.index]
              if (!item) return null
              return (
                <div
                  key={v.key}
                  data-index={v.index}
                  ref={virtualizer.measureElement}
                  data-phase={item.kind === "phase-sep" ? item.phase : undefined}
                >
                  {item.kind === "phase-sep" ? (
                    <PhaseSeparator label={item.label} description={item.description} ts={item.ts} />
                  ) : (
                    <LogRow
                      entry={eventToLogEntry(item.ev)}
                      traceback={item.ev.type === "error" ? item.ev.traceback : undefined}
                      expanded={expandedRows.has(item.key)}
                      onToggle={() => toggleExpanded(item.key)}
                    />
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {showPill && (
        <div className="flex h-(--log-pill-bar-h) items-center justify-center" data-testid="log-jump-bar">
          <Button type="button" size="xs" onClick={jumpToLatest} className="touch-hit rounded-full shadow-md">
            <ArrowDown aria-hidden />
            {newCount > 0 ? newEventsLabel(newCount) : "Jump to latest"}
          </Button>
        </div>
      )}

      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {announcement}
      </div>
    </div>
  )
})

