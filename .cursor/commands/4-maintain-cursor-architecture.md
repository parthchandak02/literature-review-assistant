# Maintain Cursor Architecture

Run a periodic cleanup pass to keep `.cursor` contracts, docs, and code references in sync.

## Steps

1. **Inventory canonical docs first** -- Read `.cursor/docs/INDEX.md`, then read every `.cursor/docs/*.md` using its lifecycle routing guidance as the ordering source.
2. **Inventory operational control plane** -- Read `.cursor/rules/**/*.mdc`, `.cursor/commands/*.md`, `.cursor/skills/**/SKILL.md`, and `.cursor/agents/*.md`.
3. **Run parity checks** --
   - `uv run python scripts/check_spec_endpoint_parity.py`
   - If workflow behavior changed, run replay validation command from `0-session-bootstrap.md`.
4. **Find drift** --
   - Missing/renamed file references
   - Rules contradicting current code paths
   - Skills contradicting lifecycle contracts in `.cursor/docs/PIPELINE.md`
5. **Apply minimal fixes** -- Update only stale docs/rules/skills/commands. Keep behavior statements code-grounded.
6. **Re-verify** -- Re-run endpoint parity and re-read changed files for consistency.
7. **Report** -- Provide concise table: file, drift found, action taken.
8. **Commit/push handoff note** -- If this audit runs before commit/push, mark doc-audit status explicitly as:
   - `PASS` (no blocking drift), or
   - `FAIL` (must-fix items listed)

## Rules

- Keep `.cursor/docs/*` as canonical.
- Keep root `AGENTS.md` and `ARCHITECTURE.md` as thin mirrors.
- Keep `.cursor/docs/API_ENDPOINTS.md` as the endpoint parity anchor (never as primary architecture source).
- Never patch run artifacts under `runs/` as a documentation fix.
