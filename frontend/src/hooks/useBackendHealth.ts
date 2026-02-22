import { useCallback, useEffect, useRef, useState } from "react"

export interface BackendHealth {
  isOnline: boolean
  checking: boolean
}

/**
 * Polls /api/health every `intervalMs` milliseconds.
 * Assumes online initially to avoid a flash of the offline banner on startup.
 * Uses an 8-second fetch timeout to accommodate cloudflared QUIC->TCP fallback latency.
 * Requires 2 consecutive failures before setting isOnline=false to suppress transient
 * QUIC packet-loss blips that resolve on the next poll.
 */
export function useBackendHealth(intervalMs = 6000): BackendHealth {
  const [isOnline, setIsOnline] = useState(true)
  const [checking, setChecking] = useState(false)
  const mountedRef = useRef(true)
  const failStreakRef = useRef(0)

  const check = useCallback(async () => {
    if (mountedRef.current) setChecking(true)
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 8000)
    try {
      // Any HTTP response (200, 404, 500) means the server socket is reachable.
      // Only a thrown TypeError (connection refused, DNS, abort timeout) means offline.
      await fetch("/api/health", { signal: controller.signal })
      failStreakRef.current = 0
      if (mountedRef.current) setIsOnline(true)
    } catch {
      failStreakRef.current += 1
      if (failStreakRef.current >= 2) {
        if (mountedRef.current) setIsOnline(false)
      }
    } finally {
      clearTimeout(timer)
      if (mountedRef.current) setChecking(false)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    check()
    const id = setInterval(check, intervalMs)
    return () => {
      mountedRef.current = false
      clearInterval(id)
    }
  }, [check, intervalMs])

  return { isOnline, checking }
}
