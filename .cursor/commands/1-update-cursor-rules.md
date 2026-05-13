# Maintain Cursor Surface

Run a single maintenance pass for `.cursor` assets and docs parity against the current codebase.

## Steps

1. **Inventory the control surface**
   - Read `.cursor/docs/INDEX.md` first.
   - List and skim: `.cursor/docs/*`, `.cursor/rules/**`, `.cursor/commands/*`, `.cursor/skills/**/SKILL.md`, `.cursor/agents/*`, plus root `README.md` and `AGENTS.md`.

2. **Survey real implementation**
   - Check `src/`, `frontend/`, `config/`, `tests/`.
   - Verify `pyproject.toml`, `frontend/package.json`, and `ecosystem.config.js`.
   - Run recent history checks (`git log`, `git status`) before changing docs/rules.

3. **Find drift**
   - Broken paths or renamed modules.
   - Rules/skills/commands contradicting code behavior.
   - Docs missing implemented behavior that is now required for safe operation.

4. **Update minimally**
   - Edit only stale content.
   - Keep one canonical location per concept where possible.
   - Do not add new rule files unless recurring behavior lacks coverage.

5. **Run required parity checks**
   - `uv run python scripts/check_spec_endpoint_parity.py`
   - `uv run pytest tests/unit/test_spec_endpoint_parity.py -q`
   - If pipeline behavior changed, run replay validation from `.cursor/commands/0-session-bootstrap.md`.

6. **Re-verify and report**
   - Re-read changed files for consistency.
   - Report touched assets in a concise table:

   | Asset File | Category | Action | What Changed |
   |------------|----------|--------|--------------|
   | (path relative to `.cursor/`) | Rule / Command / Skill / Agent / Doc | Updated / Created / Removed | Brief description |

## Rules for This Command

- Keep `.cursor/docs/*` as canonical contract docs.
- Keep `.cursor/docs/API_ENDPOINTS.md` as the endpoint parity anchor.
- Keep changes lean: prefer merges and pointer updates over adding new markdown.
- Never patch `runs/` artifacts to solve process or docs drift.
