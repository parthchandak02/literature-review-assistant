---
name: prototype
description: Build constrained throwaway prototypes to validate risky designs quickly without violating project invariants.
---

# Prototype (Constrained)

Use this skill when there is design uncertainty and a fast experiment can reduce risk before full implementation.

## Trigger and Scope

- Trigger: user asks for prototype/spike, or there are multiple plausible designs with unclear tradeoffs.
- Scope: short-lived validation artifacts and decision support.
- Out of scope: production hardening, complete feature delivery, or bypassing established contracts.

## Required Inputs

- `.cursor/docs/INDEX.md`
- One relevant domain contract from `.cursor/docs/`
- Relevant module entrypoints in `src/` or `frontend/src/`

## Operating Rules

1. Time-box prototype work and state a clear success/failure signal.
2. Keep prototype seams explicit (feature flag, isolated module, script, or branch-local path).
3. Do not patch `runs/` artifacts or runtime DB outputs.
4. If prototype crosses phase boundaries, keep typed models at boundaries (`src/models/` contracts remain authoritative).
5. Prefer deterministic checks over subjective output inspection.
6. Convert winning prototype to a production slice with tests before declaring completion.

## Expected Outputs

- A concise verdict: keep, discard, or iterate
- Evidence from commands/tests that support the verdict
- Clear next implementation slice if promoted

## Stop and Escalation Rules

- Stop if prototype requires weakening always-on invariants.
- Stop if result cannot be evaluated deterministically.
- Escalate when tradeoffs impact architecture across multiple lifecycle stages.

## Verification Checklist

- Prototype purpose and success criterion documented in chat
- No edits under `runs/`
- Boundary typing preserved where applicable
- At least one deterministic validation command executed
- Promotion path to production implementation stated
