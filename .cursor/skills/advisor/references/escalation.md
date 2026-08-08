# Escalation Reference

## Decision tree

```text
Task started
  |
  +-- Clear path from code, docs, and a focused probe?
  |     |
  |     +-- Yes: execute without escalation.
  |     |
  |     +-- No: costly to reverse and still uncertain?
  |             |
  |             +-- Yes: Tier 2 panel, if budget remains.
  |             |
  |             +-- No: Tier 1 advisor, if budget remains.
  |                     |
  |                     +-- Still stuck with new evidence?
  |                             |
  |                             +-- Yes: Tier 2 or ask the user.
  |                             +-- No: continue execution.
```

## Repo grounding for briefings

Include paths and constraints from:

- `AGENTS.md`
- `.cursor/docs/INDEX.md`
- `.cursor/docs/ARCHITECTURE.md`
- `.cursor/docs/IMPLEMENTATION_STATUS.md` when gates or phase status matter

Always restate lit-review invariants when the stuck point touches pipeline,
persistence, LLM config, or manuscript/export contracts:

- no `runs/` patches
- typed `src/models/` boundaries
- model ids from `config/settings.yaml`

## Tier 1 briefing template

Open a separate Claude chat or stronger-model thread and paste:

```text
Readonly advisor, Tier 1. Do not use tools or implement.

Goal:
<one or two sentences>

Stuck because:
<the decision, failure, or ambiguity>

Tried and observed:
<focused probes, commands, errors, or findings>

Relevant paths and constraints:
<files, compatibility, tests, scope, performance, security>
Repo docs consulted: AGENTS.md / .cursor/docs/INDEX.md / ARCHITECTURE.md
Invariants: no runs/ patches; typed src/models/; models from config/settings.yaml

Respond with exactly one first-line label:
PLAN | CORRECTION | STOP

Then provide concise guidance only.
```

## Tier 2 consultation templates

Run independent consultations. If parallel chats are unavailable, use separate
sequential stronger-model asks with the same evidence and distinct prompts.

### Implementation consultation

```text
Readonly advisor panel, implementation lane. Do not use tools or implement.

Goal: <goal>
Candidate approach: <lean hypothesis>
Files and constraints: <paths and constraints>
Repo contracts: AGENTS.md, .cursor/docs/ARCHITECTURE.md
Invariants: no runs/ patches; typed src/models/; models from config/settings.yaml

Return: recommended approach, file-level steps, validation plan, and what not
to do.
```

### Adversarial consultation

```text
Readonly advisor panel, adversarial lane. Do not use tools or implement.

Goal: <goal>
Proposed approach: <hypothesis>
Evidence: <paths, probes, constraints>

Find concrete failure modes, compatibility breaks, data loss risks, test gaps,
operational regressions, and documentation drift.

Return: ranked risks (blocker, should-fix, nit) and cheapest mitigations.
```

### Contract consultation

```text
Readonly advisor panel, contract lane. Do not use tools or implement.

List every interface, schema, protocol, storage format, and compatibility
promise touched by this proposal. For each, identify owners, callers, tests,
migration needs, and likely gaps. Prefer typed contracts under src/models/ and
canonical docs under .cursor/docs/.

Return: a gap list or a complete parity plan.
```

## Anti-patterns

Do not escalate:

- Before reading the relevant code and documentation under `.cursor/docs/`.
- To decide between styles already established by project conventions.
- For a simple factual lookup or direct test failure with an obvious fix.
- Repeatedly for the same stuck point without new evidence.
- As a substitute for asking the user when only the user can set product scope.
- To justify patching `runs/` artifacts instead of fixing process code in `src/`.
