# Session Bootstrap

Use this command as a thin launcher into canonical skill workflows.

## Canonical source

- Primary workflow owner: `.cursor/skills/general-rules/SKILL.md`
- Lifecycle routing source: `.cursor/docs/INDEX.md`
- Domain implementation flow: `.cursor/skills/build-phase/SKILL.md`

## Quick bootstrap sequence

1. Read `AGENTS.md` and `.cursor/docs/INDEX.md`.
2. Apply `general-rules` session bootstrap workflow.
3. Load only routed docs/skills needed for the request.
4. Review recent git context before edits.
5. Run task-appropriate verification checks before claiming completion.

## Optional accelerators

- For broad codebase orientation, use Repomix (`pack_codebase`) or fallback to `git ls-files` + `rg`.
- For build-phase implementation work, switch to `build-phase` immediately after routing.

## Mandatory exceptions

- Never patch `runs/` artifacts to fix behavior.
- If docs conflict with code, trust code and active rules, then report drift.
