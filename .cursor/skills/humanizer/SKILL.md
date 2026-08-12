---
name: humanizer
description: Use when the user wants to write, rewrite, or review content to sound fully human — passing AI detectors AND reading like a real person with opinions. Covers vocabulary blacklisting, 33 structural anti-patterns, 7 statistical metrics, channel-specific rules (LinkedIn, Email, Slack, Blog, Newsletter), severity tiers, and a post-rewrite verification loop.
---

# Humanizer Skill

Runtime canonical source: `reference/humanizer-skill.md` (loaded by `src/writing/prompts/humanizer_prompt.py`).

This Cursor skill adds channel-specific rules and voice-calibration UX on top of the canonical runtime source. For the full pattern catalog (all 33 anti-patterns), vocabulary blacklists, 7 statistical metrics, detection guidance, severity tiers, and verification loop, read `reference/humanizer-skill.md`.

## Core Principle

AI text is predictable. Human text is chaotic.

Goal: **controlled chaos** — text that sounds like a real person with opinions, experiences, and an imperfect but authentic writing style, AND clears statistical AI detector metrics.

Two failure modes exist. Fix both:
1. **Voice failure** — sounds like a corporate manual or chatbot
2. **Statistical failure** — passes the read test but trips pattern/metric detectors

**No-fabrication rule (critical):** The rewrite must not contain any fact, name, number, date, quote, or citation that is not in the source text. See the canonical source for full guidance.

---

## Step 1: Detect Content Type

Classify the input before applying rules. Wrong classification = wrong ruleset.

| Type | Signal |
|------|--------|
| LinkedIn post | Short-form, hook line, no subject line |
| Email | Has a subject line or greeting/sign-off |
| Slack message | Casual, fragmented, under 300 characters typical |
| Blog/article | Over 300 words, has or should have headings |
| Newsletter | Over 300 words, direct-to-reader tone, no formal headings required |
| Academic manuscript | Systematic review section, IEEE-style register (see `humanizer_academic_overlay.md`) |

**If format is ambiguous:** flag it explicitly. "This looks like either a blog or a newsletter — applying blog rules but noting the difference."

**Mixed content** (e.g., a LinkedIn post pasted inside an email thread): apply rules for the dominant format, call out the mix.

---

## Step 2: Voice Calibration

**Always run the full review first. Offer calibration after.**

Do NOT ask for a voice sample before reviewing — users want immediate feedback. After delivering the initial review, offer: "If you share a sample of writing you want to match, I can recalibrate the rewrite to that voice."

If no sample is available: default to first-person, slightly informal, opinionated voice. A real expert does not write like a manual.

Voice defaults:
- **Point of view:** First person ("I think", "I saw") where possible
- **Opinions:** Take a clear position, do not hedge
- **Tone:** Slightly informal even in formal contexts
- **Imperfections allowed:** Sentences starting with "And", "But", "So". Very short sentences. Self-directed questions.

**Sample outranks style rules:** If the user provides a writing sample, match its habits (including em dash frequency) instead of scrubbing tells. See canonical source Voice Calibration section.

**PERSONALITY AND SOUL (gated):** Apply only for blog posts, essays, opinion, and personal writing. For encyclopedic, technical, legal, academic, or reference text, neutral and plain is the correct human voice. Do not inject opinions or first person there. Academic manuscripts: see overlay; this section does not apply.

---

## Step 3–5: Patterns, Blacklists, and Metrics

See `reference/humanizer-skill.md` for:

- **Vocabulary blacklist** (English, Italian, French, German, Spanish) with replacements
- **All 33 anti-patterns** with before/after examples, including:
  - #2 Notability name-dropping
  - #13 Passive voice/subjectless fragments (academic exception noted)
  - #17 Title case headings
  - #26 Hyphenated word pair overuse
  - #27 Persuasive authority tropes
  - #28 Signposting announcements
  - #29 Fragmented headers
  - #30 Diff-anchored writing
  - #31 Manufactured punchlines/staccato drama
  - #32 Aphorism formulas
  - #33 Conversational rhetorical openers
- **7 statistical metrics** (TTR, burstiness, bigram repetition, connective density, opener diversity, compressibility, punctuation entropy)
- **Detection guidance** (false positives, clusters, preserve human signals)
- **Hard em dash cut rule** (with voice-sample exception)

---

## Step 6: Channel-Specific Rules

### LinkedIn

**Goal:** Stage 1 (distribution — hook + broad reach) → Stage 2 (dwell, saves, comments)

**Algorithm intelligence:**
- Saves = 5× weight of a like
- Substantive comments (10+ words) are heavily weighted
- Dwell time matters — short posts that get re-read beat long posts that get scrolled

**Scoring targets (1–10 scale):**

| Dimension | Target |
|-----------|--------|
| Hook strength | 8–10 |
| Originality | 7–10 |
| Readability | 7–9 (7th–9th grade) |
| Domain credibility | 7–10 |
| AI-Likeness | 1–3 (lower = better) |

**Specific rules:**
- Open with a fact, number, short statement, or provocative question — NEVER "In today's..."
- No listicle bait ("3 things I learned...")
- No engagement bait closers ("What do you think? Drop a comment below!")
- No "I'm excited to share..."
- Passive voice: flag if more than 15% of sentences
- Question-to-answer ratio: if 3+ rhetorical questions all get tidy lessons, flag the rhythm as AI pattern

### Email

**Goal:** Clear, direct, human tone. No corporate formality.

**Scoring targets:**

| Dimension | Target |
|-----------|--------|
| Clarity | 8–10 |
| Tone | 7–10 |
| AI-Likeness | 1–3 (lower = better) |

**Specific rules:**
- No "I hope this email finds you well" or any variant
- No "Please don't hesitate to reach out"
- No "As per my previous email"
- No "I'm circling back on" — say what you want directly
- Subject lines: specific fact > clever > vague
- Readability: conversational, not 7th-grade target (that's LinkedIn-specific)

### Slack

**Goal:** Casual, scannable, fast. No corporate register.

**Scoring targets:**

| Dimension | Target |
|-----------|--------|
| Brevity | 8–10 |
| Conversational fit | 8–10 |
| AI-Likeness | 1–2 (lower = better) |

**Specific rules:**
- Max 3–4 sentences per message
- No bolding, no lists in casual messages
- No "Happy to jump on a call" — say "Want to talk?" or "Can we call?"
- No sign-offs ("Best," "Thanks," "Regards")
- Emoji allowed if the channel culture uses them — but never in formal channels

### Blog / Article

**Goal:** Readable, opinionated, well-sourced. 7th–9th grade reading level.

**Scoring targets:**

| Dimension | Target |
|-----------|--------|
| Hook strength | 7–9 |
| Originality | 8–10 |
| Readability | 7–9 (7th–9th grade) |
| Domain credibility | 7–10 |
| AI-Likeness | 1–3 (lower = better) |

**Specific rules:**
- Open with a scene, number, or question — never a definition
- Avoid H2 headers that are just topic labels ("Introduction", "Conclusion")
- No "In conclusion" — end with a specific call to action or open question
- Cite every claim that needs a source with a real name + year
- "Could a 14-year-old follow this?" — if no, simplify

### Newsletter

**Goal:** Direct-to-reader, warm but substantive. Hybrid of email and blog.

**Scoring targets:**

| Dimension | Target |
|-----------|--------|
| Hook strength | 8–10 |
| Reader connection | 8–10 |
| Readability | 7–9 |
| AI-Likeness | 1–3 (lower = better) |

**Specific rules:**
- "You" language is expected and encouraged
- Short sections with clear line breaks
- No formal academic tone
- One clear point per edition — do not write a roundup of roundups

---

## Step 7–10: Severity, Verification, and Checklist

See `reference/humanizer-skill.md` for:

- **Severity tiers** (HIGH / MEDIUM / LOW)
- **Step 8:** Anti-pattern pass before delivering
- **Step 9:** Post-rewrite verification loop
- **Step 10:** Final pass/fail checklist
- **Practical before/after example**

---

## Invocation Modes

| Mode | When | Deliver |
|------|------|---------|
| Pasted text (default) | User gives text in chat | Draft, audit bullets, final rewrite |
| File mode | User points at a file | Rewrite file in place; summary in chat |
| Embedded mode | Another agent uses this as a step | Final text only, no ceremony |

For manuscript sections, runtime uses **embedded mode** via `humanizer_prompt.py`.

---

## Process Loop

1. Read input and identify all pattern instances
2. Write a draft rewrite (natural aloud, varied sentence length, appropriate register)
3. Ask: "What makes this obviously AI?" and "Did I fabricate any facts?"
4. Revise into final rewrite (no em dashes unless voice sample overrides)

In pasted-text mode, deliver draft + audit + final. In file and embedded modes, deliver only what the mode requires.

---

## Language Support

This skill applies to: **English, Italian, French, Spanish, German**

Blacklists and statistical metric benchmarks are language-specific. When content is not in English, apply the corresponding language's blacklist from the canonical source.

---

## Notes on Limitations

- **Post-rewrite verification is the most commonly skipped step** — do not skip it. Rewrites routinely introduce new AI patterns.
- **Severity tiers prevent flag fatigue** — always lead with HIGH items or users will ignore everything.
- **Voice calibration improves output quality** but is not required on first pass.
- **Self-update / pattern logging**: if running in an agentic context (Claude Code, file-editing scripts), new patterns discovered during a review can be appended to the blacklist. In standard chat context, suggest the update to the user instead.
