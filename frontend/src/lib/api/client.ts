export const API_BASE = "/api"

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

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init)
  if (!res.ok) {
    let detail: unknown = await res.text()
    try {
      detail = JSON.parse(String(detail))
    } catch {
      // keep text detail
    }
    throw new APIResponseError(`Request failed: ${path}`, res.status, detail)
  }
  if (res.status === 204) {
    return undefined as T
  }
  return res.json() as Promise<T>
}
