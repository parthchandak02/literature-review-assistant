---
name: maintain-verification-litreview
description: Daily/post-PR maintenance for verify-litreview skill and feature map. pstack maintain-verification-skill equivalent.
---

# maintain-verification-litreview

Run after setup UI or config API changes, or daily on active scoping work.

## Checklist

1. `uv run python .cursor/skills/verify-litreview/control_litreview.py doctor --json`
2. `uv run python .cursor/skills/verify-litreview/control_litreview.py phase1-gate --json`
3. `uv run python scripts/check.py api` — endpoint parity if routers changed
4. Update `verify-litreview/references/features/*` if wizard steps or API fields changed
5. Confirm SR replay still passes: `uv run python .cursor/skills/verify-litreview/control_litreview.py sr-regression --json`

## When scoping Phase 2+ lands

- Add scoping replay to `make check-local` (when `runtime_scoping.db` exists)
- Extend feature map with OSF gate, PRISMA-ScR sections
- Add `replay-workflow --profile scoping-local` to maintain loop
