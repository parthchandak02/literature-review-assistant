# AGENTS

Single onboarding entrypoint for any agentic dev tool.

If you read only one file, read this one first.

## Fast Start (under 2 minutes)

1. Read `.cursor/docs/INDEX.md`
2. Read one task-specific contract doc from `.cursor/docs/`
3. Read one relevant skill in `.cursor/skills/**/SKILL.md`

Required for planning/editing sessions: `.cursor/commands/0-session-bootstrap.md`
Optional for quick read-only questions.

## Non-Cursor Tools

If your tool does not auto-load `.cursor/rules/`, use explicit file reads:

1. `AGENTS.md`
2. `.cursor/docs/INDEX.md`
3. One task doc under `.cursor/docs/`
4. One relevant skill under `.cursor/skills/**/SKILL.md`

## Source of Truth Priority

1. Code in `src/` and `frontend/src/`
2. Always-on rules in `.cursor/rules/core/`
3. Canonical docs in `.cursor/docs/`
4. Endpoint parity anchor (`.cursor/docs/API_ENDPOINTS.md` Section 10.1 only)

If sources conflict, follow this order and verify in code.

## Minimal Task Routing

- Architecture or behavior questions -> `.cursor/docs/ARCHITECTURE.md`
- Pipeline/phase work -> `.cursor/docs/PIPELINE.md`
- API work -> `.cursor/docs/API_CONTRACT.md`
- DB/runtime state work -> `.cursor/docs/PERSISTENCE.md`
- Frontend flow work -> `.cursor/docs/UI_ARCHITECTURE.md`
- LLM/cost work -> `.cursor/docs/LLM_AND_COSTS.md`
- Validation/readiness -> `.cursor/docs/IMPLEMENTATION_STATUS.md`

## Hard Constraints

- Never patch artifacts under `runs/` to fix process behavior.
- Use typed contracts from `src/models/` at phase boundaries.
- Keep model ids configured in `config/settings.yaml`.
- Preserve endpoint parity anchor in `.cursor/docs/API_ENDPOINTS.md` Section 10.1.

## Commit and Push

Before `git commit` or `git push`, follow `.cursor/commands/3-pre-commit-workflow.md` (mandatory docs audit agent and user reminder before commit).

## Compatibility Notes

- `.cursor/docs/API_ENDPOINTS.md` is parity-only, not primary architecture guidance.
