export const CSV_REQUIRED_COLS = ["Title"]
export const CSV_EXPECTED_COLS = ["Authors", "Year", "Source title", "DOI", "Abstract", "Link", "Author Keywords"]

export function isCsvFileName(name: string): boolean {
  return /\.csv$/i.test(name.trim())
}

export function csvTypeError(file: File): string | null {
  if (isCsvFileName(file.name)) return null
  return `"${file.name}" is not a CSV file. Choose a .csv export (for example from Scopus).`
}

export interface CsvAnalysis {
  rowCount: number
  headers: string[]
  presentExpected: string[]
  missingExpected: string[]
  missingRequired: string[]
  valid: boolean
  error: string | null
}

function parseCsvHeaderRow(line: string): string[] {
  const cols: string[] = []
  let cur = ""
  let inQuotes = false
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (ch === '"') {
      inQuotes = !inQuotes
    } else if (ch === "," && !inQuotes) {
      cols.push(cur.trim().replace(/^"|"$/g, ""))
      cur = ""
    } else {
      cur += ch
    }
  }
  cols.push(cur.trim().replace(/^"|"$/g, ""))
  return cols
}

export function countCsvDataRows(text: string): number {
  let records = 0
  let inQuotes = false
  let hasContent = false
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (ch === '"') {
      inQuotes = !inQuotes
      hasContent = true
    } else if (ch === "\n" && !inQuotes) {
      if (hasContent) records++
      hasContent = false
    } else if (!/\s/.test(ch)) {
      hasContent = true
    }
  }
  if (hasContent) records++
  return Math.max(0, records - 1)
}

export async function analyzeCsvFile(file: File): Promise<CsvAnalysis> {
  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onerror = () =>
      resolve({ rowCount: 0, headers: [], presentExpected: [], missingExpected: CSV_EXPECTED_COLS, missingRequired: CSV_REQUIRED_COLS, valid: false, error: "Failed to read file" })
    reader.onload = (e) => {
      const text = (e.target?.result ?? "") as string
      if (!text) {
        resolve({ rowCount: 0, headers: [], presentExpected: [], missingExpected: CSV_EXPECTED_COLS, missingRequired: CSV_REQUIRED_COLS, valid: false, error: "File is empty" })
        return
      }
      const firstNl = text.indexOf("\n")
      const headerLine = firstNl === -1 ? text : text.slice(0, firstNl).replace(/\r$/, "")
      const headers = parseCsvHeaderRow(headerLine)
      const rowCount = countCsvDataRows(text)
      const missingRequired = CSV_REQUIRED_COLS.filter((c) => !headers.includes(c))
      const presentExpected = CSV_EXPECTED_COLS.filter((c) => headers.includes(c))
      const missingExpected = CSV_EXPECTED_COLS.filter((c) => !headers.includes(c))
      resolve({
        rowCount,
        headers,
        presentExpected,
        missingExpected,
        missingRequired,
        valid: missingRequired.length === 0 && rowCount > 0,
        error: null,
      })
    }
    reader.readAsText(file, "utf-8")
  })
}
