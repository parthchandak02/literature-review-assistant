import { useCallback, useEffect, useRef, useState } from "react"

export interface BackendHealth {
  isOnline: boolean
  checking: boolean
}

/**
 * Polls /api/health every `intervalMs` milliseconds.
 * Assumes online initially to avoid a flash of the offline banner on startup.
 * Uses a 3-second fetch timeout so a hung backend is detected quickly.
 */
export function useBackendHealth(intervalMs = 6000): BackendHealth {
  const [isOnline, setIsOnline] = useState(true)
  const [checking, setChecking] = useState(false)
  const mountedRef = useRef(true)

  const check = useCallback(async () => {
    if (mountedRef.current) setChecking(true)
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 3000)
    try {
      const res = await fetch("/api/health", { signal: controller.signal })
      if (mountedRef.current) setIsOnline(res.ok)
    } catch {
      // Network failure or timeout -- backend is offline
      if (mountedRef.current) setIsOnline(false)
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
