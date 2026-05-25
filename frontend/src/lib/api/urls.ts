const BASE = "/api"

export function downloadUrl(path: string): string {
  return `${BASE}/download?path=${encodeURIComponent(path)}`
}

export function submissionZipUrl(runId: string): string {
  return `${BASE}/run/${runId}/submission.zip`
}

export function studyFilesZipUrl(runId: string): string {
  return `${BASE}/run/${runId}/studies-files.zip`
}
