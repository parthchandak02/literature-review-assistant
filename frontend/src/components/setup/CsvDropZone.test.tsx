// @vitest-environment jsdom
import "@/test/dom"
import { useState } from "react"
import { describe, expect, it } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { CsvDropZone } from "./CsvDropZone"
import { countCsvDataRows, csvTypeError, isCsvFileName } from "./csvUtils"
import type { CsvMode } from "./types"

function Harness() {
  const [file, setFile] = useState<File | null>(null)
  const [mode, setMode] = useState<CsvMode>("supplementary")
  return <CsvDropZone file={file} onFile={setFile} mode={mode} onModeChange={setMode} />
}

async function openSection() {
  const user = userEvent.setup()
  render(<Harness />)
  await user.click(screen.getByRole("button", { name: /CSV import/ }))
  return user
}

describe("csv file type checks", () => {
  it("matches .csv case-insensitively", () => {
    expect(isCsvFileName("export.csv")).toBe(true)
    expect(isCsvFileName("EXPORT.CSV")).toBe(true)
    expect(isCsvFileName("export.xlsx")).toBe(false)
  })

  it("counts data rows with or without a trailing newline and quoted newlines", () => {
    expect(countCsvDataRows("Title\nA\nB\n")).toBe(2)
    expect(countCsvDataRows("Title\nA\nB")).toBe(2)
    expect(countCsvDataRows('Title,Abstract\nA,"line1\nline2"\n\n')).toBe(1)
    expect(countCsvDataRows("Title\n")).toBe(0)
  })

  it("explains wrong file types", () => {
    expect(csvTypeError(new File(["x"], "notes.pdf"))).toMatch(/"notes.pdf" is not a CSV file/)
    expect(csvTypeError(new File(["x"], "Scopus.CSV"))).toBeNull()
  })
})

describe("CsvDropZone", () => {
  it("is reachable by keyboard through a labelled file input", async () => {
    await openSection()
    const input = screen.getByLabelText(/Drop a CSV file here/)
    expect(input).toHaveAttribute("type", "file")
    input.focus()
    expect(input).toHaveFocus()
  })

  it("shows the mode consequence inline and switches with the radio group", async () => {
    const user = await openSection()
    expect(screen.getByText(/Skips database search/)).toBeVisible()
    expect(screen.getByText(/Runs the database search, then adds your CSV rows/)).toBeVisible()
    const master = screen.getByRole("radio", { name: /Use as master list/ })
    await user.click(master)
    expect(master).toBeChecked()
  })

  it("shows an inline error for a wrong file type", async () => {
    await openSection()
    const input = screen.getByLabelText(/Drop a CSV file here/)
    fireEvent.change(input, { target: { files: [new File(["a"], "list.txt", { type: "text/plain" })] } })
    expect(screen.getByRole("alert")).toHaveTextContent('"list.txt" is not a CSV file')
  })

  it("accepts an upper-case .CSV and reports parse results", async () => {
    await openSection()
    const input = screen.getByLabelText(/Drop a CSV file here/)
    fireEvent.change(input, { target: { files: [new File(["Title,DOI\nA,1\nB,2\n"], "SCOPUS.CSV", { type: "text/csv" })] } })
    expect(await screen.findByText("2 papers ready to screen")).toBeInTheDocument()
  })

  it("reports a missing required column inline", async () => {
    await openSection()
    const input = screen.getByLabelText(/Drop a CSV file here/)
    fireEvent.change(input, { target: { files: [new File(["Name,DOI\nA,1\n"], "bad.csv", { type: "text/csv" })] } })
    expect(await screen.findByText("Missing required column: Title")).toBeInTheDocument()
  })
})
