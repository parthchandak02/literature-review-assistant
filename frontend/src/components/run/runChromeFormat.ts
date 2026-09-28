const USD_2DP = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

export function formatChromeCost(value: number): string {
  return value > 0 && value < 0.01 ? "<$0.01" : USD_2DP.format(value)
}

export function formatOutcome(included: number | null, records: number | null): string | null {
  if (included != null && records != null) {
    return `${included.toLocaleString()} included of ${records.toLocaleString()} records`
  }
  if (included != null) return `${included.toLocaleString()} included`
  if (records != null) return `${records.toLocaleString()} records`
  return null
}
