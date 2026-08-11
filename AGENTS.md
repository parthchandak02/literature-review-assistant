# AGENTS

Single onboarding entrypoint for any agentic dev tool.

If you read only one file, read this one first.

## Fast Start (under 2 minutes)

1. Read `docs/CONTEXT.md`
2. Read one task-specific contract doc from `docs/`
3. Read one relevant skill in `.cursor/skills/**/SKILL.md`
4. For session startup: `.cursor/skills/bootstrap/SKILL.md`
5. For cross-cutting defaults: `.cursor/skills/general-rules/SKILL.md`

## Non-Cursor Tools

If your tool does not auto-load `.cursor/rules/`, use explicit file reads:

1. `AGENTS.md`
2. `docs/CONTEXT.md`
3. One task doc under `docs/`
4. One relevant skill under `.cursor/skills/**/SKILL.md`

## Source of Truth Priority

1. Code in `src/` and `frontend/src/`
2. Always-on rules in `.cursor/rules/core/`
3. Canonical docs in `docs/`
4. Endpoint parity anchor (`docs/API.md#rest-endpoints` Section 10.1 only)

If sources conflict, follow this order and verify in code.

## Minimal Task Routing

- Architecture or behavior questions -> `docs/ARCHITECTURE.md`
- Pipeline/phase work -> `docs/ARCHITECTURE.md#pipeline`
- API work -> `docs/API.md`
- DB/runtime state work -> `docs/ARCHITECTURE.md#persistence`
- Frontend flow work -> `docs/UI.md`
- LLM/cost work -> `docs/ARCHITECTURE.md#llm-and-costs`
- Validation/readiness -> `docs/TASKS.md`
- Scripts / ops commands -> `docs/SCRIPTS.md` or `./scripts/help.sh`

## Hard Constraints

- Never patch artifacts under `runs/` to fix process behavior.
- Use typed contracts from `src/models/` at phase boundaries.
- Keep model ids configured in `config/settings.yaml`.
- Preserve endpoint parity anchor in `docs/API.md#rest-endpoints` Section 10.1.

## Commit and Push

Use `.cursor/skills/commit/SKILL.md` (`/commit`).

If the change is **high level** (architecture, phases, API, persistence, frontend phase alignment, or `docs/`), run the **Before you commit** section in `docs/TASKS.md` first.

## Compatibility Notes

- `docs/API.md#rest-endpoints` is parity-only, not primary architecture guidance.
