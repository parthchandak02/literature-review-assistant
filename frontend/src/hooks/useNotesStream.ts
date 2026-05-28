import { useEffect } from "react"
import { subscribeNotesStream, type NotesStreamEvent } from "@/lib/api"

export function useNotesStream(onMessage: (event: NotesStreamEvent) => void): void {
  useEffect(() => {
    return subscribeNotesStream(onMessage)
  }, [onMessage])
}
