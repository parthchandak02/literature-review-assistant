export const API_BASE = "/api"

const API_FAILURE_DETAIL_LIMIT = 240

export class APIResponseError extends Error {
  status: number
  detail: unknown

  constructor(message: string, status: number, detail: unknown) {
    super(message)
    this.name = "APIResponseError"
    this.status = status
    this.detail = detail
  }
}

function clipDetail(text: string): string {
  const trimmed = text.trim()
  if (trimmed.length <= API_FAILURE_DETAIL_LIMIT) return trimmed
  return `${trimmed.slice(0, API_FAILURE_DETAIL_LIMIT)}...`
}

/** Short reason from a failed response body. Empty when the body has nothing useful to show. */
function detailText(detail: unknown): string {
  if (typeof detail === "string") {
    const text = detail.trim()
    if (!text) return ""
    if (text.startsWith("<")) return "the server sent a web page instead of data"
    return clipDetail(text)
  }
  if (Array.isArray(detail)) {
    const parts: string[] = []
    for (const item of detail) {
      if (parts.length >= 3) break
      const text = detailText(item)
      if (text) parts.push(text)
    }
    return parts.join("; ")
  }
  if (detail && typeof detail === "object") {
    const record = detail as { detail?: unknown; message?: unknown; msg?: unknown; loc?: unknown }
    if ("detail" in record) {
      const nested = detailText(record.detail)
      if (nested) return nested
    }
    if (typeof record.message === "string") {
      const message = detailText(record.message)
      if (message) return message
    }
    if (typeof record.msg === "string") {
      const msg = detailText(record.msg)
      if (!msg) return ""
      const loc = Array.isArray(record.loc)
        ? record.loc
            .filter((part) => typeof part === "string" || typeof part === "number")
            .join(".")
        : ""
      return loc ? `${loc}: ${msg}` : msg
    }
  }
  return ""
}

function apiFailureMessage(path: string, detail: unknown): string {
  const reason = detailText(detail)
  if (!reason) return `Request failed: ${path}`
  return `Request failed: ${path}: ${reason}`
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init)
  if (!res.ok) {
    let detail: unknown = await res.text()
    try {
      detail = JSON.parse(String(detail))
    } catch {
      // keep text detail
    }
    throw new APIResponseError(apiFailureMessage(path, detail), res.status, detail)
  }
  if (res.status === 204) {
    return undefined as T
  }
  return res.json() as Promise<T>
}
