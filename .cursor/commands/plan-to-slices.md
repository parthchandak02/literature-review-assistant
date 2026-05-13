# Plan to Slices

Convert an approved plan into small, independent implementation slices that are easy to test and review.

## Inputs

- Approved plan (from chat or `.cursor/plans/`)
- Current lifecycle stage from `.cursor/docs/INDEX.md`
- Current repository state (`git status`, recent commits)

## Steps

1. **Extract deliverables**
   - List concrete outcomes implied by the plan.
   - Remove vague tasks that do not change behavior or contracts.

2. **Define vertical slices**
   - Build slices that each include behavior + validation.
   - Prefer slices that touch one primary boundary at a time (e.g., API, orchestration, persistence, UI, docs/rules).

3. **Set acceptance for each slice**
   - Assign one deterministic check per slice (test command, replay command, or contract verification).
   - Include rollback criteria when a slice increases risk.

4. **Sequence by dependency**
   - Order from least-coupled to most-coupled.
   - Keep each slice mergeable without waiting for future slices.

5. **Track execution**
   - Mark one slice `in_progress` at a time in the todo tool.
   - Update status immediately after validation passes.

## Output Format

Produce a concise list:

- Slice name
- Files/surfaces touched
- Validation command
- Done criteria

## Guardrails

- Do not invent new architecture when an existing seam supports the slice.
- Do not split slices so small that validation overhead dominates value.
- Do not bundle unrelated risks in a single slice.
- For pipeline behavior changes, include replay-oriented validation where applicable.
