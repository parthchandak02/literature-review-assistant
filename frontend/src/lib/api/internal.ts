import { APIResponseError } from "./client"

export { API_BASE } from "./client"

/** Extract a human-readable message from a non-OK response. */
export async function apiError(res: Response, label: string): Promise<Error> {
  let detail: unknown = `HTTP ${res.status}`
  let message = `HTTP ${res.status}`
  try {
    const body = (await res.json()) as { detail?: unknown }
    if ("detail" in body) {
      detail = body.detail
      if (typeof body.detail === "string") {
        message = body.detail
      } else if (
        body.detail &&
        typeof body.detail === "object" &&
        "message" in body.detail &&
        typeof (body.detail as { message?: unknown }).message === "string"
      ) {
        message = (body.detail as { message: string }).message
      }
    }
  } catch {
    // ignore parse error; use status code
  }
  return new APIResponseError(`${label}: ${message}`, res.status, detail)
}
