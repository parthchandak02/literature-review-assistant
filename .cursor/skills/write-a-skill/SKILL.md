---
name: write-a-skill
description: Creates or refines project skills with clear triggers, compact instructions, and reusable structure. Use when the user asks to create, import, tailor, merge, or clean up skills under `.cursor/skills/`.
disable-model-invocation: true
---

# Write A Skill

Use this workflow to create high-signal skills for this repository.

## 1) Discovery

Confirm:

- purpose and scope
- target location (`.cursor/skills/` for project skills)
- trigger scenarios
- required output style
- whether to import near-verbatim or tailor

Ask focused follow-ups when ambiguity changes implementation.

## 2) Design

Define:

- `name` (lowercase + hyphens, <=64 chars)
- precise `description` with trigger terms and "Use when ..."
- guardrails and non-goals
- output contract (checklist/template/workflow)

## 3) Implementation

Create:

- `skill-name/SKILL.md` (required)
- optional support files (`REFERENCE.md`, `EXAMPLES.md`, scripts) only if needed

Keep `SKILL.md` concise. Prefer progressive disclosure over long monolith files.

## 4) Consolidation

When multiple skills overlap:

- merge generic duplicates
- keep domain-specialized skills separate
- tighten descriptions so auto-selection is unambiguous
- define one canonical owner skill per workflow area and make adjacent skills reference it

Prefer editing existing skills over introducing additional skill directories.

## 5) Verification

Check:

- description includes clear trigger language
- terminology is consistent with repo docs and rules
- references point to valid paths
- no contradiction with `AGENTS.md` and `.cursor/docs/INDEX.md`

Use lints/diagnostics if available for changed files.

## Scope boundary

This skill owns skill authoring/refactoring only.  
For general coding workflow, commit hygiene, or session bootstrap, use `general-rules`.

## Repository guardrails

- Do not create skills in `~/.cursor/skills-cursor/`.
- Respect documentation discipline: do not create extra markdown docs unless requested.
- Preserve core project invariants (no patching `runs/`, use typed contracts, avoid hardcoded model IDs).
