import { ArtifactFileList, type ArtifactFileListProps } from "@/components/results/ArtifactFileList"

export type ResultsPanelProps = ArtifactFileListProps

export function ResultsPanel(props: ResultsPanelProps) {
  return <ArtifactFileList {...props} />
}
