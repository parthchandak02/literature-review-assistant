import type { Dispatch, SetStateAction } from "react"
import type { NavigateFunction } from "react-router-dom"
import type { RunTab, SelectedRun } from "@/context/runSessionTypes"
import type { useLiveRunStream } from "@/hooks/useLiveRunStream"

type LiveStream = ReturnType<typeof useLiveRunStream>

/** Live stream fields required by navigation actions (e.g. handleSelectLiveRun). */
export type RunSessionLiveNavigationSlice = Pick<
  LiveStream,
  "liveRunId" | "liveTopic" | "liveWorkflowId" | "liveStartedAt" | "status"
>

/** Live stream fields required by connect/begin live run actions. */
export type RunSessionLiveConnectSlice = Pick<
  LiveStream,
  | "reset"
  | "setLiveRunId"
  | "setLiveTopic"
  | "setLiveStartedAt"
  | "setLiveWorkflowId"
  | "liveRunNavigatedRef"
  | "wasStreamingRef"
>

export type RunSessionLiveConnectDeps = Pick<
  RunSessionActionDeps,
  "navigate" | "selectedRun" | "setSelectedRun" | "setActiveRunTab"
> & {
  live: RunSessionLiveConnectSlice
}

/** Live stream fields required by lifecycle actions (start, cancel, history select, resume). */
export type RunSessionLiveLifecycleSlice = RunSessionLiveNavigationSlice &
  RunSessionLiveConnectSlice &
  Pick<LiveStream, "abort" | "clearLiveRunUi">

export type RunSessionLifecycleActionDeps = Pick<
  RunSessionActionDeps,
  "navigate" | "selectedRun" | "setSelectedRun" | "setActiveRunTab"
> & {
  live: RunSessionLiveLifecycleSlice
}

export interface RunSessionActionDeps {
  navigate: NavigateFunction
  selectedRun: SelectedRun | null
  setSelectedRun: Dispatch<SetStateAction<SelectedRun | null>>
  setActiveRunTab: Dispatch<SetStateAction<RunTab>>
  setHistoryOutputs: Dispatch<SetStateAction<Record<string, string>>>
  setSubmissionFocusTarget: Dispatch<SetStateAction<"reference-papers" | null>>
  setSubmissionFocusToken: Dispatch<SetStateAction<number>>
  live: RunSessionLiveNavigationSlice
}

/** Full args for `useRunSessionActions` (live stream is the complete hook return). */
export type RunSessionActionsArgs = Omit<RunSessionActionDeps, "live"> & {
  live: LiveStream
}
