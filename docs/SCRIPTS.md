# Scripts

Plain-language index for `scripts/`. Agents: read this before adding or invoking operational scripts.

**Quick terminal index:** `./scripts/help.sh` or `make scripts-help`

## Intent routing

| I need to... | Command |
|--------------|---------|
| Restart API after `src/` changes | `make pm2-restart` or `./scripts/ops_pm2.sh restart` |
| Build frontend + serve on production URL | `make deploy-prod` or `./scripts/ops_pm2.sh restart --prod-ui` |
| Run all tests before commit | `make check-local` |
| Run full pre-release gate | `make check-release` |
| Verify API docs match FastAPI routes | `make check-api` or `uv run python scripts/check.py api` |
| Verify replay test fixture schema | `uv run python scripts/check.py replay-fixture` |
| Validate a workflow `runtime.db` replay | `uv run python scripts/check.py replay-workflow --workflow-id wf-XXXX --profile local --fail-on-error` |
| Generate `config/review.yaml` from a question | `uv run python scripts/review.py start --question "..."` |
| Monitor workflow progress (low noise) | `uv run python scripts/review.py watch --workflow-id wf-XXXX` |
| Print run diagnostics | `uv run python scripts/review.py info --workflow-id wf-XXXX` |
| Regenerate manuscript appended sections | `uv run python scripts/repair.py finalize --run-dir runs/<run_id>` |
| Re-run failed LLM extraction | `uv run python scripts/repair.py re-extract --run-dir runs/<run_id>` |
| Inject missing citations into manuscript | `uv run python scripts/repair.py inject-citations --workflow-id wf-XXXX` |
| Rebuild `tests/fixtures/replay` after schema change | `uv run python scripts/repair.py regen-replay-fixture --workflow-id wf-XXXX` |
| Hermes host maintenance | `./scripts/hermes.sh maintain` |

## Entrypoints

Only these files are user-facing CLIs. Implementation lives in `scripts/lib/`.

| Script | Subcommands / modes | Purpose |
|--------|---------------------|---------|
| `scripts/ops_pm2.sh` | `restart`, `sync`, `help` | PM2 process control (`litreview-api`, `litreview-ui`, `litreview-tunnel`) |
| `scripts/check.sh` | `local`, `release` | Full test suites (ruff, pytest, frontend, replay) |
| `scripts/check.py` | `api`, `replay-fixture`, `replay-workflow` | Individual quality checks |
| `scripts/review.py` | `start`, `watch`, `info` | Review workflow operator tools |
| `scripts/repair.py` | `finalize`, `re-extract`, `inject-citations`, `regen-replay-fixture` | Fix old or broken runs |
| `scripts/hermes.sh` | `maintain`, `link-skill`, `help` | Hermes operator setup (see staleness warning in script) |
| `scripts/help.sh` | (no args) | Print this routing table in the terminal |

## Makefile targets

| Target | Alias | Runs |
|--------|-------|------|
| `check-local` | `local-ci` | `./scripts/check.sh local` |
| `check-release` | `release-check` | `./scripts/check.sh release` |
| `check-api` | `parity` | `scripts/check.py api` |
| `check-replay-fixture` | | `scripts/check.py replay-fixture` |
| `pm2-restart` | | `./scripts/ops_pm2.sh restart` |
| `deploy-prod` | | `./scripts/ops_pm2.sh restart --prod-ui` |
| `scripts-help` | | `./scripts/help.sh` |

## Naming conventions

Use lay-friendly names in new entrypoints:

- **check** — automated tests and quality gates (not `ci`)
- **repair** — fix existing runs or fixtures (not `maint` / maintenance)
- **review** — operator tools around running reviews
- **ops_pm2** — server/process operations

Subcommand names should describe the action (`api`, `replay-workflow`) not internal jargon (`parity`, `replay-validate`).

## Adding or changing scripts

1. Prefer a subcommand on an existing entrypoint over a new top-level script.
2. Put implementation in `scripts/lib/`; keep entrypoints thin.
3. Add argparse `--help` (Python) or `help` subcommand (shell).
4. Update this file and `scripts/help.sh`.
5. Update README utility table if entrypoints change.
6. Wire into `scripts/check.sh` / Makefile / `.github/workflows/ci.yml` if it is a release gate.
7. Update `.pre-commit-config.yaml` if it should run on every commit.
8. GitHub Actions (`.github/workflows/ci.yml`) runs `make check-local` after `pnpm install`; keep in sync with `scripts/check.sh local`.

## Related docs

- Verification gates: `docs/TASKS.md`
- API parity contract: `docs/API.md` Section 10.1
- PM2 reminder: `.cursor/rules/core/pm2-restart.mdc`
