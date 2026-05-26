/** Set in vite.config.ts `define` when running `vite build`. */
export const FRONTEND_BUILD_STAMP: string =
  typeof __FRONTEND_BUILD_STAMP__ !== "undefined" ? __FRONTEND_BUILD_STAMP__ : ""

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"])

/** True for production bundles served off localhost (tunnel, deployed host, LAN IP). */
export function shouldShowFrontendBuildStamp(): boolean {
  if (import.meta.env.DEV) return false
  if (!FRONTEND_BUILD_STAMP) return false
  if (typeof window === "undefined") return false
  return !LOCAL_HOSTS.has(window.location.hostname)
}
