import { describe, expect, it } from "vitest"
import {
  HISTORY_REFRESH_MS,
  LIVE_COST_REFRESH_MS,
  LIVE_DB_REFRESH_MS,
  nextWatcherFallbackDelay,
  resolveHistoryRefetchInterval,
  resolveLiveQueryRefetchInterval,
  WATCHER_FALLBACK_INITIAL_MS,
  WATCHER_FALLBACK_MAX_MS,
} from "./pollingBackoff"

describe("resolveLiveQueryRefetchInterval", () => {
  it("returns false when not live", () => {
    expect(
      resolveLiveQueryRefetchInterval(LIVE_COST_REFRESH_MS, {
        isLive: false,
        isSSEConnected: true,
      }),
    ).toBe(false)
  })

  it("returns false when SSE is connected for a live run", () => {
    expect(
      resolveLiveQueryRefetchInterval(LIVE_DB_REFRESH_MS, {
        isLive: true,
        isSSEConnected: true,
      }),
    ).toBe(false)
  })

  it("returns the base interval when live but SSE is not connected yet", () => {
    expect(
      resolveLiveQueryRefetchInterval(LIVE_COST_REFRESH_MS, {
        isLive: true,
        isSSEConnected: false,
      }),
    ).toBe(LIVE_COST_REFRESH_MS)
  })
})

describe("resolveHistoryRefetchInterval", () => {
  it("returns false when SSE owns updates for the active live run", () => {
    expect(resolveHistoryRefetchInterval(true, true)).toBe(false)
  })

  it("returns HISTORY_REFRESH_MS otherwise", () => {
    expect(resolveHistoryRefetchInterval(true, false)).toBe(HISTORY_REFRESH_MS)
    expect(resolveHistoryRefetchInterval(false, true)).toBe(HISTORY_REFRESH_MS)
    expect(resolveHistoryRefetchInterval(false, false)).toBe(HISTORY_REFRESH_MS)
  })
})

describe("nextWatcherFallbackDelay", () => {
  it("doubles delay up to the configured cap", () => {
    expect(nextWatcherFallbackDelay(WATCHER_FALLBACK_INITIAL_MS)).toBe(60_000)
    expect(nextWatcherFallbackDelay(60_000)).toBe(120_000)
    expect(nextWatcherFallbackDelay(WATCHER_FALLBACK_MAX_MS)).toBe(WATCHER_FALLBACK_MAX_MS)
  })
})
