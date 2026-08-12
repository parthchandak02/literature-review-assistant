export const HISTORY_REFRESH_MS = 30_000
export const LIVE_COST_REFRESH_MS = 5_000
export const LIVE_DB_REFRESH_MS = 10_000
export const WATCHER_FALLBACK_INITIAL_MS = 30_000
export const WATCHER_FALLBACK_MAX_MS = 120_000

export interface LiveRefetchInput {
  isLive: boolean
  isSSEConnected?: boolean
}

/** Pause react-query polling when SSE already streams live run updates. */
export function resolveLiveQueryRefetchInterval(
  baseIntervalMs: number,
  input: LiveRefetchInput,
): number | false {
  if (!input.isLive) return false
  if (input.isSSEConnected) return false
  return baseIntervalMs
}

/** Pause sidebar history polling while SSE streams the active live run. */
export function resolveHistoryRefetchInterval(
  isRunning: boolean,
  isViewingLiveRun: boolean,
): number | false {
  if (isRunning && isViewingLiveRun) return false
  return HISTORY_REFRESH_MS
}

export function nextWatcherFallbackDelay(
  currentMs: number,
  maxMs: number = WATCHER_FALLBACK_MAX_MS,
): number {
  return Math.min(currentMs * 2, maxMs)
}
