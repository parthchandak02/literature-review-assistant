---
name: prototype
description: Build constrained throwaway prototypes to validate risky designs quickly without violating project invariants. Use when prototyping or exploring a few design options.
---

# Prototype (Constrained)

Use this skill when there is design uncertainty and a fast experiment can reduce risk before full implementation.

A prototype is throwaway code that answers one question. The question decides
the shape: UI-shaped ("what should this look like") or logic-shaped ("does
this state model / data shape hold up").

## Trigger and Scope

- Trigger: user asks for prototype/spike, or there are multiple plausible designs with unclear tradeoffs.
- Scope: short-lived validation artifacts and decision support.
- Out of scope: production hardening, complete feature delivery, or bypassing established contracts.

## Required Inputs

- `docs/CONTEXT.md`
- One relevant domain contract from `docs/`
- Relevant module entrypoints in `src/` or `frontend/src/`

## Ground rules (apply to every prototype)

1. **State the question first.** One sentence, at the top of the prototype file or in your response, before writing code.
2. **Throwaway from day one.** Name files and code so it is obviously disposable (`prototype`, `PROTOTYPE`, a scratch route, a debug-only target).
3. **One command to run.** Use whatever the host project already uses (`uv run`, `pnpm`, Makefile targets); do not add a new package manager, runtime, or task runner just for this.
4. **In-memory by default.** No real database or persistent store unless the question is specifically about persistence; then use an obviously-scratch store.
5. **No live side effects.** Never mutate production systems or send real external communications from a prototype. Stub or mock any such calls.
6. **Skip polish.** No tests beyond the deterministic check needed for a verdict, minimal error handling, no abstractions beyond what keeps it runnable.
7. **Surface state.** After every action or variant switch, show the full relevant state so the answer is visible, not inferred.
8. **Clean up when done.** Once the question is answered, fold the winning code into the real codebase (rewritten to production standard) and delete the rest. Do not leave prototype code or scratch routes lying around.

## Lit-review invariants

1. Time-box prototype work and state a clear success/failure signal.
2. Keep prototype seams explicit (feature flag, isolated module, script, or branch-local path).
3. Do not patch `runs/` artifacts or runtime DB outputs.
4. If prototype crosses phase boundaries, keep typed models at boundaries (`src/models/` contracts remain authoritative).
5. Prefer deterministic checks over subjective output inspection.
6. Convert winning prototype to a production slice with tests before declaring completion.
7. Route via `docs/CONTEXT.md`; do not bypass established lifecycle contracts.

## Pick a branch

Identify which question is being answered, from the request or surrounding code:

- **"What should this look like?"** -> UI-shaped. Follow [references/UI.md](references/UI.md).
- **"Does this logic / state model / data shape hold up?"** -> Logic-shaped. Follow [references/LOGIC.md](references/LOGIC.md).

If ambiguous, default to what surrounding code suggests (a UI component or page in `frontend/src/` -> UI-shaped; a module, service, or data model in `src/` -> logic-shaped) and state the assumption up front.

## Expected Outputs

- A concise verdict: keep, discard, or iterate
- Evidence from commands/tests that support the verdict
- Clear next implementation slice if promoted
- What was learned and which variant (or pieces) won

## Stop and Escalation Rules

- Stop if prototype requires weakening always-on invariants.
- Stop if result cannot be evaluated deterministically.
- Escalate when tradeoffs impact architecture across multiple lifecycle stages.

## Verification Checklist

- Prototype purpose and success criterion documented in chat
- No edits under `runs/`
- Boundary typing preserved where applicable (`src/models/`)
- At least one deterministic validation command executed
- Promotion path to production implementation stated
- Throwaway prototype code cleaned up (or cleanup scheduled in next steps)
