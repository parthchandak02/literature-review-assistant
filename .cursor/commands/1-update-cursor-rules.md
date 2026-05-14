# Maintain Cursor Surface

Use this command as a thin launcher for `.cursor` maintenance and drift cleanup.

## Canonical sources

- Workflow owner: `.cursor/skills/general-rules/SKILL.md`
- Skill authoring/refactor owner: `.cursor/skills/write-a-skill/SKILL.md`
- Lifecycle router: `.cursor/docs/INDEX.md`

## Quick maintenance sequence

1. Route scope via `.cursor/docs/INDEX.md`.
2. Run `general-rules` bootstrap workflow before edits.
3. Identify drift across docs/rules/commands/skills and implementation.
4. Consolidate duplicated process guidance into canonical skills.
5. Keep commands lean and pointer-based.

## Parity checks (when touched scope requires)

- `uv run python scripts/check_spec_endpoint_parity.py`
- `uv run pytest tests/unit/test_spec_endpoint_parity.py -q`
- If pipeline behavior changed, run replay validation via `general-rules` guidance.

## Output requirement

Report touched `.cursor` assets in a concise table:

| Asset File | Category | Action | What Changed |
|------------|----------|--------|--------------|
| (path relative to `.cursor/`) | Rule / Command / Skill / Agent / Doc | Updated / Created / Removed | Brief description |

## Rules for this command

- Keep `.cursor/docs/*` as canonical contract docs.
- Keep `.cursor/docs/API_ENDPOINTS.md` as the endpoint parity anchor.
- Keep changes lean: prefer merges and pointer updates over new markdown.
- Never patch `runs/` artifacts to solve process or docs drift.
