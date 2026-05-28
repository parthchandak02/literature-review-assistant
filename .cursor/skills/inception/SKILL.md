---
name: inception
description: |
  Extracts reusable knowledge from work sessions into project skills, gotchas, or doc updates.
  Triggers: (1) /inception to review session learnings, (2) "save this as a skill" or
  "extract a skill from this", (3) "what did we learn?", (4) after non-obvious debugging,
  resume/replay surprises, PM2/API reliability work, or pipeline behavior that docs do not cover.
disable-model-invocation: true
---

# Inception

Continuous learning for this repository: codify non-obvious discoveries so future agents do not re-discover them.

Inspired by [Claudeception](https://github.com/blader/Claudeception); tailored to literature-review-assistant conventions.

## Core principle

Not every task becomes a skill. Extract only knowledge that is **reusable**, **non-trivial**, **verified**, and **specific** enough to trigger correctly later.

## When to extract

Extract when the session involved:

1. **Non-obvious debugging** — root cause took meaningful investigation; error message was misleading
2. **Project-specific patterns** — resume semantics, PM2 ops, DB path resolution, SSE/history quirks
3. **Pipeline surprises** — phase checkpoints, rollback behavior, included-cohort truth, artifact paths
4. **Tool integration gaps** — PydanticAI, aiosqlite, Vite proxy, PM2 restart timing not covered by docs
5. **Workflow optimizations** — replay/resume commands, monitor scripts, verification sequences that worked

Skip extraction for: one-off typos, generic Python/React advice, or anything already in `AGENTS.md` / `.cursor/docs/`.

## Where knowledge goes

| Knowledge type | Primary target | When |
|----------------|----------------|------|
| Repeatable workflow or domain procedure | `.cursor/skills/<name>/SKILL.md` | Multi-step process with clear triggers |
| Single operational quirk | `.cursor/rules/core/gotchas-agent.mdc` | One bullet; symptom → fix |
| Architecture / contract change | Relevant `.cursor/docs/*.md` | User asked or change is high-level |
| Session transfer only | Use `handoff` skill | No durable reuse expected |

**Never** store fixes as guidance to patch `runs/` artifacts. Process fixes belong in `src/` or `frontend/src/`.

## Extraction process

### Step 1 — Check existing knowledge

Search before creating:

```bash
rg --files -g 'SKILL.md' .cursor/skills
rg -i "keyword|error phrase|module name" .cursor/skills .cursor/rules/core/gotchas-agent.mdc .cursor/docs
```

| Found | Action |
|-------|--------|
| Nothing related | Create new skill or gotcha |
| Same trigger, same fix | Update existing; bump skill version if present |
| Same trigger, different cause | New skill + cross-link |
| Partial overlap | Add variant subsection to existing skill |
| Stale/wrong | Deprecate in Notes; point to replacement |

Also read `write-a-skill` before authoring or merging skills.

### Step 2 — Identify the knowledge

Answer:

- What was the problem or task?
- What was non-obvious?
- Exact trigger conditions (errors, endpoints, phase names, PM2 process names)?
- How was it verified?

### Step 3 — Research (when appropriate)

Search external docs when the fix depends on library/framework behavior (PydanticAI, FastAPI, Vite, statsmodels, etc.).

Skip search for repo-internal semantics (resume rollback, `workflows_registry.db`, cohort tables).

### Step 4 — Choose artifact type

**New skill** — use when triggers and steps will recur across sessions.

**Gotcha bullet** — use when one symptom/fix pair fits `gotchas-agent.mdc` format:

```markdown
### Short title
One or two sentences: symptom, actual cause, fix. Include exact endpoint/phase/table names.
```

**Doc update** — only for contract-level changes; follow `.cursor/docs/INDEX.md` routing.

### Step 5 — Write the skill

Use [skill-template.md](skill-template.md). Required frontmatter:

```yaml
---
name: kebab-case-name
description: |
  Third-person description with WHAT and WHEN. Include exact error messages,
  phase names, API paths, and "Use when ..." trigger phrases.
disable-model-invocation: true  # omit only if skill should auto-invoke
---
```

Repository guardrails for all extracted content:

- Skills live in `.cursor/skills/<name>/SKILL.md` only (not `~/.cursor/skills-cursor/`)
- Descriptions in third person; max 1024 chars
- Link canonical paths from `AGENTS.md` instead of duplicating architecture
- No secrets, `.env` values, or tunnel URLs
- Preserve invariants: typed `src/models/` boundaries, `config/settings.yaml` for models, deterministic stats

### Step 6 — Verify

- [ ] Description includes specific trigger terms for discovery
- [ ] Solution was verified in this session (test, replay, or API check)
- [ ] No duplication of existing skill or gotcha
- [ ] No guidance to edit `runs/` artifacts
- [ ] Paths and process names match repo (`litreview-api`, `litreview-ui`, `litreview-tunnel`)

## Retrospective mode (`/inception`)

When invoked explicitly at end of session:

1. **Review** conversation for extractable knowledge
2. **List** candidates with one-line justification each
3. **Prioritize** top 1–3 by reuse value
4. **Extract** — create or update skills/gotchas
5. **Summarize** what was saved and where

Output format:

```markdown
## Inception summary

### Extracted
- [skill-name or gotcha title] — why it matters

### Skipped (and why)
- [topic] — already documented / too one-off

### Suggested next reads
- [paths for the next agent]
```

## Self-reflection prompts

During work, ask:

- "What would I wish I knew before starting this?"
- "What symptom pointed here vs the actual root cause?"
- "Would `gotchas-agent.mdc` or a skill serve future agents better?"

## Anti-patterns

- Over-extraction of mundane fixes
- Vague descriptions ("helps with API issues")
- Duplicating `.cursor/docs/` or `AGENTS.md`
- Personal skills for repo-specific knowledge (prefer project `.cursor/skills/`)
- Extracting unverified theories

## Related skills

- Authoring structure: `write-a-skill`
- Session transfer without durable extraction: `handoff`
- Commit/doc hygiene after high-level changes: `general-rules`
- Live operational quirks list: `.cursor/rules/core/gotchas-agent.mdc`
