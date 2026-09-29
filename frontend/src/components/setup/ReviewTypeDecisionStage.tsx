import { useState, type ReactNode } from "react"
import { ArrowLeft, BookOpen, Map, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { ReviewTypeChoice } from "./types"
import {
  type DecisionAnswers,
  type DecisionStep,
  decisionStepPosition,
  formatDecisionStepPosition,
  nextDecisionStep,
  resolveReviewType,
} from "./reviewTypeDecisionLogic"

export type { ReviewTypeChoice } from "./types"

type TriState = "yes" | "no" | "unsure"

interface QuizFrame {
  step: DecisionStep
  answers: DecisionAnswers
}

const QUESTIONS: Record<Exclude<DecisionStep, "unsure_pick">, { icon: ReactNode; question: string; hint: string }> = {
  broad: {
    icon: <BookOpen className="h-4 w-4 text-intent-primary" />,
    question: "Is your research question broad?",
    hint: "Broad questions explore a topic area (e.g., “What is known about X?”). Narrow questions target a specific comparison or effect.",
  },
  map_evidence: {
    icon: <Map className="h-4 w-4 text-intent-primary" />,
    question: "Do you want to map the evidence?",
    hint: "Mapping catalogs what types of evidence exist and where the gaps are. That is typical of scoping reviews.",
  },
  focused_iedo: {
    icon: <BookOpen className="h-4 w-4 text-intent-primary" />,
    question: "Is it focused on a treatment, exposure, diagnosis, or outcome?",
    hint: "Questions that compare treatments, exposures, diagnostic tests, or health outcomes are common in systematic reviews.",
  },
  determine_evidence: {
    icon: <BookOpen className="h-4 w-4 text-intent-primary" />,
    question: "Do you need to determine what the evidence shows?",
    hint: "Answering a specific evidence question (effectiveness, association, diagnostic accuracy) points toward a systematic review.",
  },
}

interface ReviewTypeDecisionStageProps {
  onComplete: (reviewType: ReviewTypeChoice) => void
  onCancel?: () => void
}

export function ReviewTypeDecisionStage({ onComplete, onCancel }: ReviewTypeDecisionStageProps) {
  const [frames, setFrames] = useState<QuizFrame[]>([{ step: "broad", answers: {} }])
  const current = frames[frames.length - 1]
  const { step, answers } = current
  const recommendation = resolveReviewType(answers)

  function handleAnswer(answer: TriState) {
    const { step: nextStep, answers: patch } = nextDecisionStep(step, answer)
    const merged = { ...answers, ...patch }
    const resolved = resolveReviewType(merged)
    if (resolved && answer !== "unsure") {
      onComplete(resolved)
      return
    }
    setFrames((prev) => [...prev, { step: nextStep, answers: merged }])
  }

  function handleBack() {
    setFrames((prev) => (prev.length > 1 ? prev.slice(0, -1) : prev))
  }

  const canGoBack = frames.length > 1

  return (
    <div className="glass-panel border border-border/80 rounded-panel p-5 space-y-4" role="group" aria-label="Review type decision guide">
      <div className="flex items-center gap-2">
        {canGoBack && (
          <Button type="button" variant="ghost" size="xs" onClick={handleBack} className="text-muted hover:text-foreground">
            <ArrowLeft />
            Back
          </Button>
        )}
        <span className="text-xs text-muted" aria-live="polite">
          {formatDecisionStepPosition(decisionStepPosition(step))}
        </span>
        {onCancel && (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={onCancel}
            className="ml-auto text-muted hover:text-foreground"
            aria-label="Close decision guide"
          >
            <X />
          </Button>
        )}
      </div>

      {step === "unsure_pick" ? (
        <div className="space-y-4">
          <div className="space-y-2 text-xs text-muted leading-relaxed">
            <p className="font-medium text-foreground">Scoping vs systematic review</p>
            <ul className="list-disc pl-4 space-y-1">
              <li>
                <span className="text-foreground font-medium">Scoping</span>: maps what evidence exists,
                its concepts, and its gaps (PCC; PRISMA-ScR). Appraisal is optional.
              </li>
              <li>
                <span className="text-foreground font-medium">Systematic</span>: answers a focused question
                with appraised synthesis (PICO; PRISMA 2020; may include meta-analysis).
              </li>
            </ul>
          </div>
          {recommendation ? (
            <p className="rounded-lg border border-intent-primary-border/40 bg-intent-primary-subtle/40 px-3 py-2.5 text-xs text-foreground">
              Based on your answers, we recommend a <span className="font-semibold">{recommendation} review</span>.
            </p>
          ) : (
            <p className="text-xs text-muted">Not sure yet? Pick the review type that best matches your goal.</p>
          )}
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button type="button" size="lg" className="flex-1 font-semibold" onClick={() => onComplete(recommendation ?? "systematic")}>
              Continue with {recommendation ?? "systematic"} review
            </Button>
            <Button
              type="button"
              variant="outline"
              size="lg"
              className="flex-1"
              onClick={() => onComplete((recommendation ?? "systematic") === "systematic" ? "scoping" : "systematic")}
            >
              Choose {(recommendation ?? "systematic") === "systematic" ? "scoping" : "systematic"} instead
            </Button>
          </div>
        </div>
      ) : (
        <DecisionQuestion {...QUESTIONS[step]} onAnswer={handleAnswer} />
      )}
    </div>
  )
}

interface DecisionQuestionProps {
  icon: ReactNode
  question: string
  hint: string
  onAnswer: (answer: TriState) => void
}

const ANSWERS: ReadonlyArray<{ value: TriState; label: string }> = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
  { value: "unsure", label: "Not sure" },
]

function DecisionQuestion({ icon, question, hint, onAnswer }: DecisionQuestionProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-intent-primary-subtle border border-intent-primary-border/30">
          {icon}
        </span>
        <div className="min-w-0 space-y-1.5">
          <h3 className="text-sm font-semibold text-foreground leading-snug">{question}</h3>
          <p className="text-xs text-muted leading-relaxed">{hint}</p>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3" role="group" aria-label="Your answer">
        {ANSWERS.map(({ value, label }) => (
          <Button
            key={value}
            type="button"
            variant="outline"
            size="lg"
            className="font-medium"
            onClick={() => onAnswer(value)}
          >
            {label}
          </Button>
        ))}
      </div>
    </div>
  )
}
