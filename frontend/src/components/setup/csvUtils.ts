export const CSV_REQUIRED_COLS = ["Title"]
export const CSV_EXPECTED_COLS = ["Authors", "Year", "Source title", "DOI", "Abstract", "Link", "Author Keywords"]

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

function countCsvDataRows(text: string): number {
  // Walk the text respecting quoted fields so embedded newlines don't skew the count.
  let rows = 0
  let inQuotes = false
  let firstRow = true
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (ch === '"') {
      inQuotes = !inQuotes
    } else if (ch === "\n" && !inQuotes) {
      if (firstRow) {
        firstRow = false
      } else {
        // peek ahead: if the rest is only whitespace, don't count trailing blank line
        const rest = text.slice(i + 1).trimStart()
        if (rest.length > 0) rows++
      }
    }
  }
  // If file has no trailing newline, the last row isn't counted yet
  if (!firstRow && text.trimEnd().length > 0 && text[text.length - 1] !== "\n") rows++
  return rows
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
