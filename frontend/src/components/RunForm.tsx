import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Eye, EyeOff, Loader, Play } from "lucide-react"
import type { RunRequest } from "@/lib/api"

interface RunFormProps {
  defaultReviewYaml: string
  onSubmit: (req: RunRequest) => Promise<void>
  disabled: boolean
}

const LABEL = "block text-xs font-medium text-zinc-400 mb-1.5"
const SECTION = "bg-zinc-900 border border-zinc-800 rounded-xl p-5"

export function RunForm({ defaultReviewYaml, onSubmit, disabled }: RunFormProps) {
  const [reviewYaml, setReviewYaml] = useState(defaultReviewYaml)
  const [geminiKey, setGeminiKey] = useState("")

  // Sync textarea with the default YAML once it loads from the backend.
  // Only applies when the user has not yet typed anything.
  useEffect(() => {
    if (defaultReviewYaml && reviewYaml === "") {
      setReviewYaml(defaultReviewYaml)
    }
  }, [defaultReviewYaml]) // reviewYaml intentionally excluded -- we only want to seed, not overwrite
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
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {/* Review config */}
      <div className={SECTION}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-zinc-200">Review Configuration</h2>
          <span className="text-xs text-zinc-600">review.yaml</span>
        </div>
        <p className="text-xs text-zinc-500 mb-3 leading-relaxed">
          Edit the YAML below to configure your review topic, inclusion criteria, and database settings.
        </p>
        <Textarea
          className="font-mono text-xs min-h-[260px] resize-y bg-zinc-950 border-zinc-800 text-zinc-300 placeholder:text-zinc-700 focus-visible:ring-violet-500/50"
          value={reviewYaml}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setReviewYaml(e.target.value)}
          disabled={disabled || loading}
          placeholder="Paste your review.yaml content here..."
          spellCheck={false}
        />
      </div>

      {/* API keys */}
      <div className={SECTION}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-zinc-200">API Keys</h2>
          <button
            type="button"
            onClick={() => setShowKeys((v) => !v)}
            className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            {showKeys ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            {showKeys ? "Hide" : "Show"}
          </button>
        </div>
        <p className="text-xs text-zinc-600 mb-4 leading-relaxed">
          Keys are sent only to your local backend and never stored externally.
        </p>
        <div className="flex flex-col gap-3">
          <div>
            <label className={LABEL}>
              Gemini API Key <span className="text-red-500">*</span>
            </label>
            <Input
              type={showKeys ? "text" : "password"}
              placeholder="AIza..."
              value={geminiKey}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setGeminiKey(e.target.value)}
              disabled={disabled || loading}
              autoComplete="off"
              className="bg-zinc-950 border-zinc-800 text-zinc-200 placeholder:text-zinc-700 focus-visible:ring-violet-500/50 h-9"
            />
          </div>
          <div>
            <label className={LABEL}>OpenAlex API Key <span className="text-zinc-600">(optional)</span></label>
            <Input
              type={showKeys ? "text" : "password"}
              placeholder="optional"
              value={openalexKey}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setOpenalexKey(e.target.value)}
              disabled={disabled || loading}
              autoComplete="off"
              className="bg-zinc-950 border-zinc-800 text-zinc-200 placeholder:text-zinc-700 focus-visible:ring-violet-500/50 h-9"
            />
          </div>
          <div>
            <label className={LABEL}>IEEE Xplore API Key <span className="text-zinc-600">(optional)</span></label>
            <Input
              type={showKeys ? "text" : "password"}
              placeholder="optional"
              value={ieeeKey}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setIeeeKey(e.target.value)}
              disabled={disabled || loading}
              autoComplete="off"
              className="bg-zinc-950 border-zinc-800 text-zinc-200 placeholder:text-zinc-700 focus-visible:ring-violet-500/50 h-9"
            />
          </div>
        </div>
      </div>

      {error && (
        <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      <Button
        type="submit"
        disabled={disabled || loading}
        className="w-full h-10 bg-violet-600 hover:bg-violet-500 text-white font-medium gap-2 transition-colors"
      >
        {loading ? (
          <>
            <Loader className="h-4 w-4 animate-spin" />
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
