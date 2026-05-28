# Inception

Extract durable learnings from the current session into project skills or gotchas.

## Canonical source

- Primary workflow owner: `.cursor/skills/inception/SKILL.md`
- Skill authoring conventions: `.cursor/skills/write-a-skill/SKILL.md`
- Live operational quirks: `.cursor/rules/core/gotchas-agent.mdc`

## Quick sequence

1. Review the session for non-obvious, verified discoveries.
2. Search `.cursor/skills/` and `gotchas-agent.mdc` for existing coverage.
3. Save new knowledge to the right artifact (skill, gotcha, or doc — see inception skill routing table).
4. Summarize what was extracted, skipped, and where it lives.

## Guardrails

- Fix process in `src/` / `frontend/src/` — never encode patching `runs/` as the solution.
- Prefer project skills under `.cursor/skills/` over personal skill directories for repo-specific knowledge.
