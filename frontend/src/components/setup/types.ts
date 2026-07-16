export interface SetupViewProps {
  defaultReviewYaml: string
  onGenerateDraft: (req: ConfigGenerateRequest) => void
  onOpenDraftWithYaml: (yaml: string) => void
  disabled: boolean
}

export type CsvMode = "supplementary" | "masterlist"
export type GenerationProfile = "standard" | "health_sdg"
export interface ConfigGenerateRequest {
  question: string
  deepseekKey: string
  csvFile?: File
  csvMode: CsvMode
  generationProfile: GenerationProfile
}
