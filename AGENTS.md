# AGENTS

Single onboarding entrypoint for any agentic dev tool.

If you read only one file, read this one first.

## Fast Start (under 2 minutes)

1. Read `docs/CONTEXT.md`
2. Read one task-specific contract doc from `docs/`
3. Read one relevant skill in `.cursor/skills/**/SKILL.md`
4. For session startup: `.cursor/skills/bootstrap/SKILL.md`
5. For cross-cutting defaults: `.cursor/skills/general-rules/SKILL.md`

## Non-Cursor Tools

If your tool does not auto-load `.cursor/rules/`, use explicit file reads:

1. `AGENTS.md`
2. `docs/CONTEXT.md`
3. One task doc under `docs/`
4. One relevant skill under `.cursor/skills/**/SKILL.md`

## Source of Truth Priority

1. Code in `src/` and `frontend/src/`
2. Always-on rules in `.cursor/rules/core/`
3. Canonical docs in `docs/`
4. Endpoint parity anchor (`docs/API.md#rest-endpoints` Section 10.1 only)

If sources conflict, follow this order and verify in code.

## Production hosting

Public URL: `https://litreview.parthchandak.info` (Cloudflare Tunnel → local `:8001`). Cloudflare Access email OTP at edge; tune Application session to 30d (`720h`) so devices re-auth monthly, not daily. See [docs/agents/dashboard-hosting.md](docs/agents/dashboard-hosting.md).

## Minimal Task Routing

- Architecture or behavior questions -> `docs/ARCHITECTURE.md`
- Pipeline/phase work -> `docs/ARCHITECTURE.md#pipeline`
- API work -> `docs/API.md`
- DB/runtime state work -> `docs/ARCHITECTURE.md#persistence`
- Frontend flow work -> `docs/UI.md`
- LLM/cost work -> `docs/ARCHITECTURE.md#llm-and-costs`
- LLM provider or API key changes -> `.cursor/skills/llm-provider/SKILL.md`
- Validation/readiness -> `docs/TASKS.md`
- Scripts / ops commands -> `docs/SCRIPTS.md` or `./scripts/help.sh`
- UX before/after screenshots -> [UX screenshot harness](#ux-screenshot-harness) below

## UX screenshot harness

Developer-only Playwright helpers for visual review of the local dashboard. They are not part of the review pipeline and are not wired into `make check-local`. Outputs go under `tmp/ux-shots/<label>/` (gitignored). Requires a running UI (API on `:8001` or the Vite proxy) and a local Playwright Chromium install (`pip install playwright && playwright install chromium`).

| Script | Purpose | Entrypoint |
|--------|---------|------------|
| `scripts/ux_screenshots.py` | Capture desktop (dark/light) and mobile shots of Setup, Activity, Results, Data, Config, and Cost | `python3 scripts/ux_screenshots.py <label> [--base http://localhost:8001]` |
| `scripts/ux_screening_preview.py` | Present a completed run as `awaiting_review` on the screening gate (rewrites history/attach GETs only; blocks other non-GET API writes) | `python3 scripts/ux_screening_preview.py <label> [--base URL] [--workflow wf-0001]` |

How to run:

```bash
# terminal 1: API serving the UI (or use Vite on :5173 and pass --base http://localhost:5173)
uv run uvicorn src.web.app:app --port 8001

# terminal 2: labeled before/after captures
python3 scripts/ux_screenshots.py before
python3 scripts/ux_screening_preview.py before-screening --workflow wf-0001
```

How to test: unit contract in `tests/unit/test_ux_screenshot_harness_docs.py` (docs + CLI shape). Manual check: open files under `tmp/ux-shots/<label>/` after a capture. Full script index: `docs/SCRIPTS.md`.

## Hard Constraints

- Never patch artifacts under `runs/` to fix process behavior.
- Use typed contracts from `src/models/` at phase boundaries.
- Keep model ids configured in `config/settings.yaml`.
- Preserve endpoint parity anchor in `docs/API.md#rest-endpoints` Section 10.1.

## Commit and Push

Use `.cursor/skills/commit/SKILL.md` (`/commit`).

If the change is **high level** (architecture, phases, API, persistence, frontend phase alignment, or `docs/`), run the **Before you commit** section in `docs/TASKS.md` first.

## Compatibility Notes

- `docs/API.md#rest-endpoints` is parity-only, not primary architecture guidance.
