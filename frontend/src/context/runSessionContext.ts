import { createContext } from "react"
import type { RunSessionContextValue } from "@/context/runSessionTypes"

export const RunSessionContext = createContext<RunSessionContextValue | null>(null)
