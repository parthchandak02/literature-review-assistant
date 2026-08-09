---
name: architecture
description: Finds architectural friction and deepens modules through small interfaces, real seams, locality, and testability. Use when planning large refactors, pass-through files pile up, invoking /architecture, or improve-codebase-architecture.
---

# Architecture Review

Read this skill as a readonly architecture review unless the user explicitly
asks for implementation. Its goal is to find where a codebase is hard to
change, understand, or verify, then present candidates before proposing a
solution.

## Read first

1. Read this repo's architecture and contributor contracts:
   - `AGENTS.md`
   - `.cursor/docs/INDEX.md`
   - `.cursor/docs/ARCHITECTURE.md`
   - `.cursor/docs/IMPLEMENTATION_STATUS.md`
2. Identify the primary stack and its natural seams (PydanticAI Graph workflow
   nodes, FastAPI control plane, SQLite repositories, typed `src/models/`
   boundaries, React UI state, export/manuscript contracts).
3. Read nearby modules and their tests before judging their shape.

If breadth would help, use optional parallel readonly explores. They are a
means to gather evidence, not a required workflow.

Do not treat a root-level `CONTEXT.md` as required. Canonical project context
lives under `.cursor/docs/` (routed by `INDEX.md`).

## Shared vocabulary

Use the terms in [references/LANGUAGE.md](references/LANGUAGE.md) consistently:
Module, Interface, Implementation, Seam, Adapter, Depth, Leverage, and
Locality. Avoid substituting loosely related terms when reviewing architecture.

The key tests are:

- Apply the deletion test to suspected pass-throughs.
- Treat the interface as the test surface.
- Do not add an adapter seam until variation makes it real.

## Review process

### 1. Explore

Map friction in the requested area:

- Where does one concept require hopping among many small files?
- Which Modules are shallow, with an Interface almost as complex as their
  Implementation?
- Which Seams leak implementation details across callers?
- Where is behavior difficult to test through its Interface?
- Where are pure helpers extracted only for tests while the important behavior
  remains scattered among callers?

Use [references/DEEPENING.md](references/DEEPENING.md) to classify dependencies
and evaluate seams.

### 2. Present candidates

Before proposing an interface or implementation, give a numbered list of
candidates. For each, include:

1. Files or Modules involved.
2. The observed friction.
3. A plain-language direction for improvement.
4. Expected Leverage, Locality, and testability gains.
5. Relevant dependency category or conflict with `.cursor/docs/` contracts.

Ask which candidate to explore. Do not treat candidate discovery as approval for
a large refactor.

### 3. Grill the chosen candidate

For terminology, scope, or contract ambiguity, load and follow the project's
`grill` skill (`.cursor/skills/grill/SKILL.md`) before a
large refactor. Use it to pressure-test the chosen candidate against docs and
code. Resolve one decision at a time:

- What behavior belongs behind the Interface?
- Where should the Seam live?
- Which invariants, errors, ordering rules, and performance expectations do
  callers need to know?
- What tests survive an internal refactor?
- Does an existing decision in `.cursor/docs/ARCHITECTURE.md` or
  `IMPLEMENTATION_STATUS.md` constrain the choice?

Update project docs under `.cursor/docs/` only when the user asks or a durable
high-level decision has been made (see `AGENTS.md` source-of-truth priority).

### 4. Compare interfaces when needed

When the user wants interface alternatives, follow
[references/INTERFACE-DESIGN.md](references/INTERFACE-DESIGN.md). Present
multiple materially different designs, compare them by Depth, Locality, and
Seam placement, then recommend one.

## Implementation handoff

After the user selects a direction, state the intended Interface, adapters,
tests, and files in scope. Keep the diff small. Replace obsolete shallow tests
with behavior tests through the new Interface rather than layering both sets.

## Lit-review invariants

Architecture candidates and follow-on diffs must preserve:

- Never patch artifacts under `runs/` to fix process behavior; deepen or fix
  code in `src/` / `frontend/src/`.
- Keep typed contracts in `src/models/` at phase boundaries.
- Resolve LLM model ids from `config/settings.yaml`, never hardcode them.
