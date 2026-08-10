---
name: advisor
description: Escalates to a stronger readonly advisor when execution is stuck: PLAN, CORRECTION, or STOP. Use when facing hard forks, contract risk, repeated failure, or unclear architecture trade-offs.
---

# Advisor

The executor drives the work: reads, tools, edits, tests, and user
communication. The advisor supplies readonly guidance only when the executor
cannot reasonably choose the next step.

The advisor does not implement, use tools, or communicate directly with the
user.

## Budget

- Use at most three escalations per task.
- Do not escalate for typos, obvious one-file fixes, clear existing conventions,
  or a task that takes one or two direct steps.
- Do not use escalation to avoid reading documentation or running an obvious
  diagnostic.
- Do not nest advisors.

If the budget is exhausted, ask the user for the decision or stop with a concise
blocker.

## Read before escalating

Before Tier 1 or Tier 2, ground the briefing in this repo's contracts:

1. `AGENTS.md`
2. `docs/CONTEXT.md`
3. `docs/ARCHITECTURE.md`
4. `docs/TASKS.md` when status, gates, or phase readiness matter

If docs and code conflict, trust code and always-on rules, then call out drift.

## When to escalate

Escalate after a focused readonly probe when one of these remains:

- An architecture fork with materially different ownership or seam placement.
- Contract risk across API, schema, persistence, concurrency, or integrations.
- A repeated failure from the same approach.
- Two or more valid designs with unclear trade-offs.
- A potentially irreversible decision with incomplete evidence.

Use [references/escalation.md](references/escalation.md) for the decision tree
and portable briefing templates.

## Tier 1: quick advisor

Open a separate Claude chat or stronger-model thread. Paste a concise briefing
and ask for exactly one first-line label:

- **PLAN**: numbered next steps.
- **CORRECTION**: what to undo, change, or retry.
- **STOP**: blocker and the one question the user must answer.

Treat the response as readonly advice. Resume execution with a PLAN or
CORRECTION when clear. Surface STOP to the user instead of guessing.

## Tier 2: adversarial panel

Use Tier 2 only when a decision is costly to reverse and uncertainty remains
after a focused probe or Tier 1 advice.

Run two or three independent readonly consultations, in parallel when available:

1. Implementation: the leanest safe way to land the change.
2. Adversarial: concrete regressions, failure modes, and cheap mitigations.
3. Optional contract: API, schema, compatibility, migration, or test gaps.

Synthesize one recommendation. For irreversible product or architecture forks,
remain advisory until the user approves the direction.

## Executor rules after advice

- Keep advisor output internal unless the user asks for design rationale.
- Apply guidance only when it fits the observed code and constraints.
- Do not re-escalate the same question without new evidence.
- Report the escalation only when STOP requires input, a Tier 2 finding changes
  the decision, or the user asks how the choice was made.

## Lit-review invariants

Any PLAN or CORRECTION that touches this codebase must preserve:

- Never patch artifacts under `runs/` to fix process behavior; fix `src/` or
  `frontend/src/`.
- Use typed contracts from `src/models/` at phase boundaries (no untyped dicts).
- Never hardcode model id strings; resolve models from `config/settings.yaml`.
