# Academic Manuscript Overlay

Apply the full humanizer skill, with the following mandatory overrides for systematic review manuscripts:

- Content type is always `academic_manuscript_section`.
- Invocation mode is **embedded**: run the draft → audit → final loop internally and output only the revised section text. No draft, audit bullets, or summary.
- Preserve formal academic register suitable for IEEE-style manuscripts.
- Do not introduce first-person anecdotes, personal opinions, or conversational asides unless they already exist in the source text.
- **PERSONALITY AND SOUL does not apply** to manuscripts. Neutral, precise, and plain is the correct human voice for academic writing. Do not inject opinions, humor, or first-person editorializing.
- Do not apply social-channel mechanics (LinkedIn, Slack, newsletter engagement patterns).
- Keep structure, headings, citation keys, and all numeric/statistical values unchanged.
- Keep edits bounded and local; avoid full rewrites when targeted edits can resolve issues.

## No-Fabrication Rule (Critical)

The rewrite must not contain any fact, name, number, date, quote, or citation that is not in the source text.

- Do not swap vague claims for invented specifics.
- Do not add study names, effect sizes, p-values, or citations not already present.
- If a sentence needs detail that is not in the source, leave it vague or cut it. Never fabricate to sound more human.
- Preserving citation keys, numeric values, percentages, confidence intervals, and p-values exactly is mandatory.

## Academic Pattern Exceptions

- **Passive voice (Pattern #13):** Acceptable and often preferred in Methods and Results when the actor is unknown or irrelevant. Do not force active voice where convention uses passive constructions.
- **Formal vocabulary:** Do not flatten legitimate academic terms (e.g., "ostensibly", "constituent") just because they sound sophisticated. Pattern #7 targets specific AI-coded words, not all formal language.
- **Em dashes (Pattern #14):** Still apply the hard cut rule unless a voice sample overrides. Academic prose rarely needs em dashes.
- **En dashes in numeric ranges:** Preserve en dashes in confidence intervals, age ranges, and score spans (e.g., `1.20–3.40`, `15–20 years`). Runtime checks flag em dashes only, not these legitimate en-dash uses.
