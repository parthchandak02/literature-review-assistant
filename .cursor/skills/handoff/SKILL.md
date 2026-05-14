---
name: handoff
description: Produces concise handoff context so another agent can continue work without re-discovery. Use when switching sessions, pausing substantial work, or transferring ownership of an in-flight task.
argument-hint: "What should the next session focus on?"
disable-model-invocation: true
---

# Handoff

Create a compact handoff for a fresh agent to continue quickly and safely.

If the user provides arguments, treat them as the next-session objective and tailor the handoff to that scope.

## Primary mode

Default to handoff content in chat.  
Create a markdown file only when the user explicitly asks for a file artifact.

If a file is requested, use a temp path from:

```bash
mktemp -t handoff-XXXXXX.md
```

Read the generated file before writing to it.

## Required sections

1. Session objective
2. Completed work
3. In-progress work
4. Blockers and risks
5. Exact next actions (ordered)
6. Suggested skills/tools for next agent
7. Reference artifacts (paths/URLs only)

## Repository-specific guidance

- Reference canonical docs via `.cursor/docs/INDEX.md` when they affect next steps.
- Include concrete verification commands when relevant (tests, replay checks, parity checks).
- Point to specific code paths in `src/` or `frontend/src/` that were touched or should be touched next.

## De-duplication rule

Do not duplicate content already captured in plans, PR descriptions, ADRs, issues, commits, or diffs.  
Link or cite those artifacts instead.

## Guardrails

- Do not invent progress.
- Do not include secrets.
- Keep it short, factual, and execution-ready.
