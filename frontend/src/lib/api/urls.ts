const BASE = "/api"

export function downloadUrl(path: string, cacheBust?: string | number): string {
  const base = `${BASE}/download?path=${encodeURIComponent(path)}`
  if (cacheBust == null) return base
  return `${base}&v=${encodeURIComponent(String(cacheBust))}`
}

export function prismaDiagramUrl(runId: string): string {
  return `${BASE}/run/${encodeURIComponent(runId)}/prisma-diagram.png`
}

export function submissionZipUrl(runId: string): string {
  return `${BASE}/run/${runId}/submission.zip`
}

export function studyFilesZipUrl(runId: string): string {
  return `${BASE}/run/${runId}/studies-files.zip`
}
