---
name: grill-with-docs
description: Runs a focused grilling session that stress-tests plans against repository contracts, terminology, and code reality. Use when the user asks to pressure-test a plan, challenge assumptions, or validate decisions against docs and implementation.
disable-model-invocation: true
---

# Grill With Docs

Interview the user relentlessly until the design is precise and internally consistent.

Ask one question at a time. Wait for the user's answer before asking the next.

For each question, include your recommended answer and why.

If a question can be answered by reading code/docs, check those first and skip asking.

## Routing and source of truth

Before challenging design details:

1. Read `AGENTS.md`
2. Read `.cursor/docs/INDEX.md`
3. Read only the routed canonical docs needed for the topic (`ARCHITECTURE.md`, `PIPELINE.md`, `IMPLEMENTATION_STATUS.md`, `API_CONTRACT.md`, `PERSISTENCE.md`, `UI_ARCHITECTURE.md`, `LLM_AND_COSTS.md`)
4. Cross-check with code in `src/` and `frontend/src/`

If docs and code conflict, trust code and active rules, then call out drift explicitly.

## Grilling behavior

### Challenge terminology

- Catch overloaded terms immediately.
- Propose a canonical term when language is fuzzy.
- Ask the user to choose one term and stick to it.

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

## Output shape per question

Use this format:

1. **Question** - one precise decision point
2. **Recommended answer** - a concrete default
3. **Why** - one to three reasons grounded in code/docs
4. **What changes if opposite choice** - impact summary
