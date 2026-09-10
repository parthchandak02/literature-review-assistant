import { useState, type ReactNode } from "react"
import { ArrowLeft, BookOpen, Map } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { ReviewTypeChoice } from "./types"
import {
  type DecisionAnswers,
  type DecisionStep,
  nextDecisionStep,
  resolveReviewType,
} from "./reviewTypeDecisionLogic"

export type { ReviewTypeChoice } from "./types"

type TriState = "yes" | "no" | "unsure"


function mergeAnswers(base: DecisionAnswers, patch: Partial<DecisionAnswers>): DecisionAnswers {
  return { ...base, ...patch }
}

const SCOPING_VS_SYSTEMATIC_COPY = (
  <div className="space-y-3 text-xs text-muted leading-relaxed">
    <p className="font-medium text-foreground">Scoping vs systematic review</p>
    <ul className="list-disc pl-4 space-y-1">
      <li>
        <span className="text-foreground font-medium">Scoping</span> — maps what evidence exists,
        concepts, and gaps (PCC; PRISMA-ScR). Optional appraisal.
      </li>
      <li>
        <span className="text-foreground font-medium">Systematic</span> — answers a focused question
        with appraised synthesis (PICO; PRISMA 2020; may include meta-analysis).
      </li>
    </ul>
  </div>
)

interface ReviewTypeDecisionStageProps {
  onComplete: (reviewType: ReviewTypeChoice) => void
  onBack?: () => void
}

export function ReviewTypeDecisionStage({ onComplete, onBack }: ReviewTypeDecisionStageProps) {
  const [step, setStep] = useState<DecisionStep>("broad")
  const [answers, setAnswers] = useState<DecisionAnswers>({})

  function handleTriStateAnswer(answer: TriState) {
    const { step: nextStep, answers: patch } = nextDecisionStep(step, answer)
    const merged = mergeAnswers(answers, patch)
    setAnswers(merged)

    const resolved = resolveReviewType(merged)
    if (resolved && answer !== "unsure") {
      onComplete(resolved)
      return
    }

    setStep(nextStep)
  }

  function handleManualPick(reviewType: ReviewTypeChoice) {
    onComplete(reviewType)
  }

  return (
    <div className="flex flex-col gap-6">
      {onBack && (
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1.5 text-xs text-muted hover:text-foreground transition-colors self-start"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back
        </button>
      )}

      <div className="text-center pt-2 pb-1">
        <p className="text-sm text-muted max-w-md mx-auto leading-relaxed">
          Choose the review type that fits your research goal. A short decision guide helps you
          pick between a scoping and systematic review.
        </p>
      </div>

      {step === "broad" && (
        <DecisionCard
          icon={<BookOpen className="h-4 w-4 text-intent-primary" />}
          question="Is your research question broad?"
          hint="Broad questions explore a topic area (e.g., “What is known about X?”). Narrow questions target a specific comparison or effect."
          onAnswer={handleTriStateAnswer}
        />
      )}

      {step === "map_evidence" && (
        <DecisionCard
          icon={<Map className="h-4 w-4 text-intent-primary" />}
          question="Do you want to map the evidence?"
          hint="Mapping catalogs what types of evidence exist and where gaps are — typical of scoping reviews."
          onAnswer={handleTriStateAnswer}
        />
      )}

      {step === "focused_iedo" && (
        <DecisionCard
          icon={<BookOpen className="h-4 w-4 text-intent-primary" />}
          question="Is it focused on an intervention, exposure, diagnosis, or outcome?"
          hint="Focused IEDO questions compare treatments, exposures, diagnostic tests, or health outcomes — common in systematic reviews."
          onAnswer={handleTriStateAnswer}
        />
      )}

      {step === "determine_evidence" && (
        <DecisionCard
          icon={<BookOpen className="h-4 w-4 text-intent-primary" />}
          question="Do you need to determine what the evidence shows?"
          hint="Answering a specific evidence question (effectiveness, association, diagnostic accuracy) points toward a systematic review."
          onAnswer={handleTriStateAnswer}
        />
      )}

      {step === "unsure_pick" && (
        <div className="glass-panel border border-border/80 rounded-xl p-5 space-y-4">
          {SCOPING_VS_SYSTEMATIC_COPY}
          {resolveReviewType(answers) ? (
            <div className="rounded-lg border border-intent-primary-border/40 bg-intent-primary-subtle/40 px-3 py-2.5">
              <p className="text-xs text-foreground">
                Based on your answers, we recommend a{" "}
                <span className="font-semibold">{resolveReviewType(answers)} review</span>.
              </p>
            </div>
          ) : (
            <p className="text-xs text-muted">
              Not sure yet? Pick the review type that best matches your goal.
            </p>
          )}
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button
              type="button"
              className="flex-1 h-11 font-semibold"
              onClick={() =>
                handleManualPick(resolveReviewType(answers) ?? "systematic")
              }
            >
              Continue with {resolveReviewType(answers) ?? "systematic"} review
            </Button>
            {resolveReviewType(answers) && (
              <Button
                type="button"
                variant="outline"
                className="flex-1 h-11"
                onClick={() =>
                  handleManualPick(resolveReviewType(answers) === "systematic" ? "scoping" : "systematic")
                }
              >
                Choose {resolveReviewType(answers) === "systematic" ? "scoping" : "systematic"} instead
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

interface DecisionCardProps {
  icon: ReactNode
  question: string
  hint: string
  onAnswer: (answer: TriState) => void
}

function DecisionCard({ icon, question, hint, onAnswer }: DecisionCardProps) {
  return (
    <div className="glass-panel border border-border/80 rounded-xl p-5 space-y-4">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-intent-primary-subtle border border-intent-primary-border/30">
          {icon}
        </span>
        <div className="min-w-0 space-y-1.5">
          <h2 className="text-sm font-semibold text-foreground leading-snug">{question}</h2>
          <p className="text-xs text-muted leading-relaxed">{hint}</p>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <Button type="button" className="h-10 font-medium" onClick={() => onAnswer("yes")}>
          Yes
        </Button>
        <Button type="button" variant="outline" className="h-10 font-medium" onClick={() => onAnswer("no")}>
          No
        </Button>
        <Button type="button" variant="secondary" className="h-10 font-medium" onClick={() => onAnswer("unsure")}>
          Not sure
        </Button>
      </div>
    </div>
  )
}
