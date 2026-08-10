---
name: grill
description: Stress-tests plans against repository contracts, terminology, and code reality. Use when pressure-testing a plan, challenging assumptions, or invoking /grill / grill-with-docs.
disable-model-invocation: true
---

# Grill

Interview the user relentlessly until the design is precise and internally consistent.

Ask one question at a time. Wait for the user's answer before asking the next.

For each question, include your recommended answer and why.

If a question can be answered by reading code/docs, check those first and skip asking.

If the user shifts to implementation ("go", "implement", "stop grilling"), confirm and end grilling mode. Do not implement during the grilling session.

## Routing and source of truth

Before challenging design details:

1. Read `AGENTS.md`
2. Read `docs/CONTEXT.md`
3. Read only the routed canonical docs needed for the topic (`docs/ARCHITECTURE.md`, `docs/ARCHITECTURE.md#pipeline`, `docs/TASKS.md`, `docs/API.md`, `docs/ARCHITECTURE.md#persistence`, `docs/UI.md`, `docs/ARCHITECTURE.md#llm-and-costs`)
4. Cross-check with code in `src/` and `frontend/src/`

If docs and code conflict, trust code and active rules, then call out drift explicitly.

Doc shapes for this repo: [references/DOC-ROUTING.md](./references/DOC-ROUTING.md).
Offer ADRs sparingly using [references/ADR-FORMAT.md](./references/ADR-FORMAT.md) only when Doc creation allows it.

## Grilling behavior

### Challenge terminology

- Catch overloaded terms immediately.
- Propose a canonical term when language is fuzzy.
- Ask the user to choose one term and stick to it.
- Prefer terms already used in `docs/`, `src/models/`, and phase/checkpoint vocabulary over inventing new ones.

### Probe boundaries with scenarios

- Use concrete edge cases (phase restarts, replay behavior, run cancellation, API/UI parity, schema truth).
- Force explicit ownership and lifecycle boundaries.

### Verify claims against implementation

- If the user states behavior, verify in code.
- If code contradicts the claim, surface the contradiction and ask which should be authoritative.

### Resolve dependencies in order

- Identify prerequisite decisions first.
- Do not move downstream until upstream choices are locked.

## Guardrails

- Do not patch `runs/` artifacts.
- Keep typed boundaries intact (`src/models/` contracts).
- Do not create markdown docs unless explicitly requested by the user.
- Keep grilling outputs concise and actionable.
- Use `docs/CONTEXT.md` for lifecycle routing; do not invent alternate context doc paths.

## Doc creation

Only create or edit docs when:
- The user explicitly asks, **or**
- Offering an ADR and the user accepts (repo already uses `docs/adr/`)

Otherwise keep settled terms in the session status output and note that docs were not written.

## Output shape per question

Use this format:

1. **Question** - one precise decision point
2. **Recommended answer** - a concrete default
3. **Why** - one to three reasons grounded in code/docs
4. **What changes if opposite choice** - impact summary
5. **Status** - `Resolved` or `Open` for that decision

## Session-end contract

At session end (or when grilling stops), report:

- **Resolved**: terms and decisions locked
- **Open**: remaining decisions and blockers
- **Next**: next question, or the first implementation step once grilling ends
