import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Eye, EyeOff, Play, RefreshCw } from "lucide-react"
import type { RunRequest } from "@/lib/api"

interface RunFormProps {
  defaultReviewYaml: string
  onSubmit: (req: RunRequest) => Promise<void>
  disabled: boolean
}

export function RunForm({ defaultReviewYaml, onSubmit, disabled }: RunFormProps) {
  const [reviewYaml, setReviewYaml] = useState(defaultReviewYaml)
  const [geminiKey, setGeminiKey] = useState("")
  const [openalexKey, setOpenalexKey] = useState("")
  const [ieeeKey, setIeeeKey] = useState("")
  const [showKeys, setShowKeys] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!geminiKey.trim()) {
      setError("Gemini API key is required.")
      return
    }
    setError(null)
    setLoading(true)
    try {
      await onSubmit({
        review_yaml: reviewYaml,
        gemini_api_key: geminiKey.trim(),
        openalex_api_key: openalexKey.trim() || undefined,
        ieee_api_key: ieeeKey.trim() || undefined,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Review Configuration</CardTitle>
          <CardDescription>
            Paste or edit your review.yaml below. The research_question field defines the topic.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Textarea
            className="font-mono text-xs min-h-[280px] resize-y"
            value={reviewYaml}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setReviewYaml(e.target.value)}
            disabled={disabled || loading}
            placeholder="Paste review.yaml content here..."
            spellCheck={false}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center justify-between">
            API Keys
            <button
              type="button"
              onClick={() => setShowKeys((v) => !v)}
              className="text-muted-foreground hover:text-foreground transition-colors"
              title={showKeys ? "Hide keys" : "Show keys"}
            >
              {showKeys ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </CardTitle>
          <CardDescription>
            Keys are sent directly to the local backend. They are never stored or transmitted
            externally.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div>
            <label className="text-sm font-medium mb-1 block">
              Gemini API Key <span className="text-destructive">*</span>
            </label>
            <Input
              type={showKeys ? "text" : "password"}
              placeholder="AIza..."
              value={geminiKey}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setGeminiKey(e.target.value)}
              disabled={disabled || loading}
              autoComplete="off"
            />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">OpenAlex API Key</label>
            <Input
              type={showKeys ? "text" : "password"}
              placeholder="optional"
              value={openalexKey}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setOpenalexKey(e.target.value)}
              disabled={disabled || loading}
              autoComplete="off"
            />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">IEEE Xplore API Key</label>
            <Input
              type={showKeys ? "text" : "password"}
              placeholder="optional"
              value={ieeeKey}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setIeeeKey(e.target.value)}
              disabled={disabled || loading}
              autoComplete="off"
            />
          </div>
        </CardContent>
      </Card>

      {error && (
        <p className="text-sm text-destructive px-1">{error}</p>
      )}

      <Separator />

      <Button type="submit" disabled={disabled || loading} className="w-full gap-2">
        {loading ? (
          <>
            <RefreshCw className="h-4 w-4 animate-spin" />
            Starting review...
          </>
        ) : (
          <>
            <Play className="h-4 w-4" />
            Start Systematic Review
          </>
        )}
      </Button>
    </form>
  )
}
