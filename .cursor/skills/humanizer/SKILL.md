---
name: humanizer
description: Use when the user wants to write, rewrite, or review content to sound fully human — passing AI detectors AND reading like a real person with opinions. Covers vocabulary blacklisting, 30 structural anti-patterns, 7 statistical metrics, channel-specific rules (LinkedIn, Email, Slack, Blog, Newsletter), severity tiers, and a post-rewrite verification loop.
---

# Humanizer Skill

Runtime canonical source: `reference/humanizer-skill.md` (loaded by `src/writing/prompts/humanizer_prompt.py`).

## Core Principle

AI text is predictable. Human text is chaotic.

Goal: **controlled chaos** — text that sounds like a real person with opinions, experiences, and an imperfect but authentic writing style, AND clears statistical AI detector metrics.

Two failure modes exist. Fix both:
1. **Voice failure** — sounds like a corporate manual or chatbot
2. **Statistical failure** — passes the read test but trips pattern/metric detectors

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

---

## Step 3: Vocabulary Blacklist — Zero Tolerance

These words are flagged by all major detectors AND make writing sound like AI output. **Never use them, not even once.**

### English (60+)
delve, tapestry, landscape (figurative), pivotal, crucial, foster, underscore, showcase, nestled, testament, enduring, garner, interplay, intricacies, intricate, myriad, plethora, multifaceted, nuanced, holistic, synergy, leverage, paradigm, robust, comprehensive, innovative, seamless, streamline, empower, facilitate, optimize, realm, beacon, harness, illuminate, bolster, noteworthy, commendable, paramount, resonate, burgeoning, nexus, palpable, transformative, foundational, advent, ethos, catalyst, spearhead, reimagine, elevate, panorama, additionally, moreover, furthermore, consequently, nevertheless, navigate (figurative), vibrant, groundbreaking, world-class, state-of-the-art, cutting-edge, unparalleled, game-changer, revolutionary, utilize, commence, endeavor, ascertain, ameliorate, notwithstanding, aforementioned, henceforth, thereby, thereof, wherein, herein

### Italian
sfaccettato, olistico, sinergia, fondamentale (overused), integrato (overused), panorama (figurative), scenario (overused), valorizzare, potenziare, approfondire, snellire, implementare, ottimizzare

### French
paysage (figurative), scenario, integre, rationaliser, valoriser, dynamiser, approfondir, implementer, optimiser

### German
Landschaft (figurative), Szenario, grundlegend (overused), ganzheitlich, Synergie, Paradigma, umfassend, innovativ, implementieren, optimieren, rationalisieren

### Spanish
panorama (figurative), implementar, optimizar, potenciar, agilizar, dinamizar, profundizar

### Replacements

| Instead of | Use |
|------------|-----|
| crucial / pivotal | important, key, what matters |
| comprehensive | complete, detailed, thorough |
| leverage | use, take advantage of |
| facilitate | help, make possible, allow |
| robust | solid, strong, reliable |
| innovative | new, different, fresh |
| seamless | smooth, without hiccups |
| moreover / furthermore | period + new sentence, "and", "also" |
| however / nevertheless | but, yet, still |
| consequently | so, then, which means |
| landscape | field, area, space, situation |
| paradigm | model, approach, way of thinking |
| foster | build, create, grow |
| delve | dig into, look at, explore |
| navigate (figurative) | deal with, handle, face, work through |
| tapestry / beacon / nexus | delete — no replacement needed |

---

## Step 4: The 30 Anti-Patterns — Precise Rules

### Content Patterns

**1. Significance inflation**
- NEVER: "stands as a testament", "serves as a reminder", "plays a vital/crucial role", "marks a pivotal moment", "indelible mark", "enduring legacy", "shaping the future"
- DO: State the fact without inflating it. "It matters" is enough.

**2. Superficial -ing phrases**
- NEVER: comma + decorative gerund: ", highlighting the...", ", underscoring the...", ", emphasizing the...", ", fostering...", ", showcasing..."
- DO: Two separate sentences. "X did Y. This shows Z."

**3. Promotional language**
- NEVER: "vibrant", "breathtaking", "must-visit", "groundbreaking", "world-class", "state-of-the-art", "cutting-edge", "unparalleled"
- DO: Describe concretely WHY something is good. Numbers, facts, direct experience.

**4. Vague attributions**
- NEVER: "experts argue", "observers have noted", "industry reports suggest", "widely regarded as", "according to some analysts"
- DO: Cite the specific source. "According to the McKinsey 2025 report..." or name the person.

**5. Challenges & prospects**
- NEVER: "despite these challenges", "challenges and opportunities", "looking ahead", "continues to thrive", "future outlook"
- DO: Be specific about WHICH challenge and HOW it is being addressed.

**6. Ghost citations**
- NEVER: "studies show", "research indicates", "data suggests", "experts agree", "science tells us"
- DO: Cite specific study with name, year, source. If you have none, write "in my experience" or "I've noticed that".

### Language & Grammar

**7. AI vocabulary** → See blacklist above. Zero tolerance.

**8. Copula avoidance**
- NEVER: "serves as a...", "stands as a...", "functions as a...", "boasts over...", "features a..."
- DO: Use "is" or "has". "Rome is the capital of Italy" — not "Rome serves as the capital."

**9. Negative parallelism**
- NEVER: "It's not X. It's Y." used more than once per text
- DO: Direct affirmative form. If contrast is needed, use "but" or "instead."

**10. Rule of three**
- NEVER: 2 or more triplet lists in the same text ("fast, reliable, and secure")
- DO: Lists of 2 or 4 items, or expand into a sentence.

**11. Synonym cycling**
- NEVER: rotating synonyms for the same noun (the protagonist → the main character → the central figure → the hero)
- DO: Pick ONE term, use pronouns for repetitions.

**12. False ranges**
- NEVER: parallel double constructions ("from X to Y, from A to B")
- DO: One range expression, or two separate sentences.

**13. Latinate vocabulary**
- NEVER: utilize (→ use), commence (→ start), endeavor (→ try), ascertain (→ find out), ameliorate (→ improve), notwithstanding, aforementioned, henceforth, thereby, thereof, wherein, herein
- RULE: If a 12-year-old would not use it, do not use it.

**14. Personification**
- NEVER: "the data tells us", "the market demands", "this approach offers a unique", "the numbers speak"
- DO: Human agent. "Looking at the data, I saw that..." or "Customers are asking for..."

### Style Patterns

**15. Em dash overuse**
- NEVER more than 1 em dash (—) per 500 words. Zero is better.
- DO: Commas, periods, parentheses instead.

**16. Boldface overuse**
- NEVER more than 3 bold words/phrases per paragraph. Zero is better in prose.
- DO: Bold is for scanning headings and lists, not body text emphasis.

**17. Inline-header lists**
- NEVER: "- **Title**: description..." as a repeated structure
- DO: Simple bullet list, or narrative paragraphs.

**18. Emoji in professional text**
- NEVER in articles, reports, or formal posts. Zero emoji.

**19. Curly quotes**
- Weak AI signal. Use straight quotes where possible.

### Communication Patterns

**20. Sycophantic tone**
- NEVER: "Great question!", "You're absolutely right", "That's an excellent point", "I hope this helps"
- DO: Answer directly without opening compliments.

**21. Cutoff disclaimers**
- NEVER: "as of my last training", "I don't have access to real-time data"

**22. Chatbot artifacts**
- NEVER: "I'd be happy to help", "feel free to ask", "as an AI", "is there anything else I can help with"
- DO: Delete entirely.

**23. Both-sides diplomacy**
- NEVER: "while some argue", "on the one hand... on the other", "pros and cons", "both perspectives have valid points"
- DO: Take a position. "I think X because..." A human has opinions.

### Filler & Hedging

**24. Filler phrases**
- NEVER: "in order to" (→ "to"), "due to the fact that" (→ "because"), "at this point in time" (→ "now"), "it is important to note that" (→ delete), "at the end of the day" (→ delete), "in terms of" (→ "for/about")
- RULE: If removing the phrase keeps the meaning, remove it.

**25. Excessive hedging**
- NEVER: "it could potentially be argued", "to some extent", "in many ways", "one might argue", "it seems that"
- DO: Assert with confidence. "It is" not "it would seem to potentially be".

**26. Generic conclusions**
- NEVER: "the future looks bright", "exciting times ahead", "one thing is certain", "a step in the right direction", "in conclusion"
- DO: End with a specific fact, a concrete recommendation, or an open question.

**27. Over-explanation**
- NEVER: "in other words", "simply put", "which means that", "to put it differently", "essentially,", "basically,"
- DO: Explain well the first time. If a second explanation is needed, the first was wrong.

### Original Patterns

**28. Navigate metaphors**
- NEVER: "navigate" used figuratively
- DO: "deal with", "handle", "face", "work through"

**29. Formulaic openings**
- NEVER: "In an increasingly...", "In today's...", "In the current landscape...", "In an ever-changing..."
- DO: Open with a fact, anecdote, question, number, or direct experience.

**30. Forced plot twists**
- NEVER: "But here's the thing...", "The real point is...", "But there's a catch..."
- DO: Build contrast narratively, not with a formula.

---

## Step 5: The 7 Statistical Metrics — Beat Every Detector

Regex/pattern checks are only 35–50% of a detection score. The rest is statistical. Pass all 7.

### Metric 1: TTR (Type-Token Ratio) — Vocabulary diversity
- **Measures:** Unique words ÷ total words, in 100-word windows
- **AI signal:** Low TTR = same words repeated
- **Fix:** Use natural synonyms where they actually fit. Vary vocabulary.
- **WARNING:** Do not overdo it — synonym cycling (Pattern #11) is also an AI signal.

### Metric 2: Sentence Burstiness
- **Measures:** Variation in sentence length (coefficient of variation)
- **AI signal:** All sentences 15–20 words each
- **Fix:** Mix aggressively:
  - Very short (3–6 words): "It works." "Not true." "I know this."
  - Medium (12–18 words): bulk of text
  - Long (25–35 words): one every 4–5 sentences, with subordinate clauses
  - Fragments: "Result? Nothing." "Classic mistake."
  - Rhetorical questions: "So what?" "Why?"

### Metric 3: Bigram Repetition
- **Measures:** Word pairs repeated too often
- **AI signal:** Same word pairs 3+ times in short text
- **Fix:** Reread and vary repeated pairs. Replace some with pronouns or restructure.

### Metric 4: Connective Density
- **Measures:** Connectives per 100 words
- **AI signal:** Too many (however, moreover, furthermore, additionally, consequently, nevertheless, therefore, thus, hence, subsequently, accordingly, likewise, similarly, ultimately, essentially, fundamentally)
- **Fix:** Maximum 1 connective per 150–200 words. Use "But" not "However". Let a period do the transition — no need to announce it.

### Metric 5: Opener Diversity
- **Measures:** Unique first 2 words relative to total sentences
- **AI signal:** Many sentences starting with "The...", "This...", "It is...", "In the..."
- **Fix:** Systematically vary the first word:
  - Start with a verb: "Look at the data."
  - Start with an adverb: "Often we forget that..."
  - Start with a conjunction: "And that changes everything." "But it is not enough."
  - Start with a number: "73% of..."
  - Start with a proper noun: "Google changed..."
  - Start with a quote: "'It will never work' — she said..."

### Metric 6: Text Compressibility
- **Measures:** Uniqueness of 4-character sequences in 500-character windows
- **AI signal:** Formulaic phrases, repetitive structures
- **Fix:** Introduce unpredictable elements: proper nouns, specific (non-round) numbers, direct quotes, domain-specific terms, personal anecdotes, original metaphors, interjections ("Look", "Right", "Well")

### Metric 7: Punctuation Entropy
- **Measures:** Shannon entropy of punctuation distribution
- **AI signal:** Only periods and commas
- **Fix:** Use ALL punctuation types:
  - Semicolon (;) — at least 1–2 per 500 words
  - Colon (:) — to introduce lists or explanations
  - Parentheses () — for asides
  - Question mark (?) — rhetorical questions
  - Exclamation mark (!) — sparingly, 1 per 300+ words max
  - Hyphen (-) — compounds or short asides
  - Ellipsis (...) — very rare, for effect
  - Quotation marks ("") — quotes and special-use terms

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

## Step 7: Severity Tiers

Not all flags are equal. Triage before rewriting.

| Tier | Meaning | Examples |
|------|---------|---------|
| 🔴 HIGH | Fix immediately — kills credibility or kills distribution | Blacklisted word, ghost citation, chatbot artifact, formulaic opener, engagement bait closer |
| 🟡 MEDIUM | Flag to editor — weakens the voice noticeably | Em dash overuse, passive voice density >15%, synonym cycling, rule-of-three overuse, connective density >1 per 100 words |
| 🟢 LOW | Consider fixing — minor statistical signal | Curly quotes, single copula construction, single filler phrase, one vague attribution |

**Always address HIGH before MEDIUM. Do not give users a wall of equal-weight flags.**

---

## Step 8: Anti-Pattern Pass (Before Delivering)

Reread the draft checking:

1. Any words from the blacklist? → Replace
2. Any of the 30 patterns? → Rephrase
3. Do sentences vary in length? → Break up or extend
4. Do sentences all start the same? → Vary openers
5. Too many connectives? → Delete, use a period
6. Is punctuation varied? → Add ; : () ? where natural
7. Any triplets (a, b, and c)? → Reduce to 2 or expand to 4
8. Passive voice >15%? → Rewrite flagged sentences
9. 3+ rhetorical Q&A loops? → Break the rhythm

---

## Step 9: Post-Rewrite Verification Loop

**Critical step — neither skill originally included this.**

After rewriting, re-run Step 8 on the output. Rewrites frequently swap one AI tell for another (e.g., removing "moreover" then writing "it is worth noting that").

Verification checklist:
- [ ] Did the rewrite introduce any new blacklisted words?
- [ ] Did sentence length variety survive the rewrite?
- [ ] Did the first-person voice survive, or did it get smoothed out?
- [ ] Is punctuation still varied?
- [ ] Are sentence openers still diverse?
- [ ] Does it still sound like a person reading it aloud?

If verification fails any item, fix and re-check once more before delivering.

---

## Step 10: Final Pass/Fail Checklist

- [ ] Zero words from the blacklist
- [ ] Zero ghost citations ("studies show" without a named source)
- [ ] Zero chatbot artifacts ("happy to help", "as an AI")
- [ ] Zero formulaic openings ("In an increasingly...", "In today's...")
- [ ] Maximum 1 em dash per 500 words
- [ ] Maximum 1 triplet (a, b, and c) in the entire text
- [ ] Maximum 1 connective (however/moreover/furthermore) per 150–200 words
- [ ] Sentences of varied lengths (at least 3 very short, 3 long per 500 words)
- [ ] At least 3 different punctuation types (. , ; : ? !)
- [ ] First words of sentences: at least 70% unique
- [ ] At least 1 personal opinion or clear position stated
- [ ] At least 1 specific detail (number, name, date, place)
- [ ] No "in conclusion" / "to sum up" at the end
- [ ] No "in other words" / "simply put" in the text
- [ ] Post-rewrite verification loop completed
- [ ] HIGH severity flags all resolved
- [ ] Text sounds like a real person reading it aloud

---

## Practical Example

### BEFORE (typical AI):
> "In today's rapidly evolving digital landscape, cybersecurity has become a crucial and pivotal concern for organizations worldwide. Moreover, the increasing sophistication of cyber threats underscores the importance of implementing robust and comprehensive security measures. Studies show that a holistic approach — one that encompasses both technical solutions and human awareness — serves as the most effective strategy. However, despite these challenges, the future outlook remains promising."

**Flags:** formulaic opener 🔴, "crucial" + "pivotal" 🔴, "moreover" 🟡, "robust" 🔴, "comprehensive" 🔴, ghost citation 🔴, "holistic" 🔴, "serves as" 🟡, "despite these challenges" 🟡, "future outlook" 🟡

### AFTER (humanized):
> "Three attacks in six months. That is what my company went through in 2025; the first one took down email for two days, the second encrypted half our servers, and the third (thankfully) we caught in time. What did I learn? Firewalls alone are not enough. You need people who can spot a suspicious email. And you need a Plan B for when Plan A fails — because it will."

**Why it works:**
- First-person experience, clear opinion
- Specific numbers (3 attacks, 6 months, 2 days)
- Varied sentence lengths (5, 20, 15, 4, 9, 16 words)
- Varied punctuation (. ; , () — ?)
- Zero blacklisted words
- Zero connectives
- Varied openers ("Three", "That", "What", "Firewalls", "You", "And")

---

## Language Support

This skill applies to: **English, Italian, French, Spanish, German**

Blacklists and statistical metric benchmarks are language-specific. When content is not in English, apply the corresponding language's blacklist section from Step 3 and flag connective density using the language's equivalents.

---

## Notes on Limitations

- **Post-rewrite verification is the most commonly skipped step** — do not skip it. Rewrites routinely introduce new AI patterns.
- **Severity tiers prevent flag fatigue** — always lead with HIGH items or users will ignore everything.
- **Voice calibration improves output quality** but is not required on first pass.
- **Self-update / pattern logging**: if running in an agentic context (Claude Code, file-editing scripts), new patterns discovered during a review can be appended to the blacklist. In standard chat context, suggest the update to the user instead — the model cannot edit this file itself.
