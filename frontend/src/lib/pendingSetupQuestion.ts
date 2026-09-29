let pendingQuestion: string | null = null

/** Question to prefill the next time the New review setup mounts. */
export function setPendingSetupQuestion(question: string | null) {
  pendingQuestion = question?.trim() ? question.trim() : null
}

/** Read and clear the pending question. */
export function takePendingSetupQuestion(): string {
  const question = pendingQuestion ?? ""
  pendingQuestion = null
  return question
}
